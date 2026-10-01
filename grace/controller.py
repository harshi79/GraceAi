"""Conversation orchestration.

:class:`GraceController` owns every rule the client must obey:

* exactly **one** Grace conversation per client session - it is either the
  most recent conversation the server reports, or a single locally minted id;
* a message is never sent while another one is streaming (duplicate-send
  protection), and a cancelled generation can never write into a newer one;
* the full history is rebuilt from the conversation on every request so stale
  state can never be transmitted;
* the ``done`` event is authoritative: ``fullContent`` replaces the streamed
  text and ``remainingCredits`` becomes the credit balance.

It has no tkinter dependency.  Events are delivered through ``on_event``
callbacks which the UI is responsible for marshalling onto the Tk main loop.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional

from . import config, modes
from .attachments import AttachmentManager
from .client import AeroClient, ChatSummary, conversation_from_chat
from .errors import AeroError, AttachmentUploadFailed, GraceInterrupted
from .logutil import log
from .models import (
    Conversation,
    Credits,
    Message,
    ROLE_ASSISTANT,
    ROLE_USER,
    StreamResult,
    new_id,
    now_iso,
)
from .modes import GraceMode

NEW_CONVERSATION_TITLE = "New conversation"


@dataclass
class Event:
    """Something the UI should react to."""

    kind: str
    data: Any = None


# Event kinds (kept as constants so typos become AttributeErrors in tests).
LOADING = "loading"
CONVERSATION_READY = "conversation_ready"
HISTORY_RESTORED = "history_restored"
USER_MESSAGE = "user_message"
ASSISTANT_START = "assistant_start"
ASSISTANT_CHUNK = "assistant_chunk"
STATUS = "status"
ASSISTANT_DONE = "assistant_done"
ASSISTANT_ERROR = "assistant_error"
ERROR = "error"
CREDITS = "credits"
TITLE = "title"
ATTACHMENT_CHANGED = "attachment_changed"
ATTACHMENTS_CLEARED = "attachments_cleared"
BUSY = "busy"
MODE_CHANGED = "mode_changed"
CONNECTION = "connection"
SHUTDOWN = "shutdown"


class GraceController:
    """State machine driving one Grace conversation."""

    def __init__(
        self,
        client: AeroClient,
        settings: Optional[config.Settings] = None,
        on_event: Optional[Callable[[Event], None]] = None,
        mode_key: str = modes.default().key,
    ) -> None:
        self.client = client
        # Copy so mutating one controller's settings cannot leak into others.
        self.settings = replace(settings or config.DEFAULT_SETTINGS)
        self._on_event = on_event
        self.mode: GraceMode = modes.get(mode_key)

        self.conversation: Optional[Conversation] = None
        self.credits = Credits()
        self.attachments = AttachmentManager(
            uploader=self._upload_attachment,
            on_change=lambda att: self._emit(Event(ATTACHMENT_CHANGED, att)),
        )

        self._busy = False
        self._send_lock = threading.RLock()
        self._cancel = threading.Event()
        self._generation = 0
        self._worker: Optional[threading.Thread] = None
        self._status = ""
        self._active_message: Optional[Message] = None

    # ------------------------------------------------------------------ #
    # Event plumbing
    # ------------------------------------------------------------------ #
    def _emit(self, event: Event) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:  # pragma: no cover - never kill the worker
            log.exception("event handler failed for %s", event.kind)

    # ------------------------------------------------------------------ #
    # Read-only state
    # ------------------------------------------------------------------ #
    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def status(self) -> str:
        return self._status

    @property
    def conversation_id(self) -> str:
        return self.conversation.id if self.conversation else ""

    @property
    def messages(self) -> List[Message]:
        return list(self.conversation.messages) if self.conversation else []

    @property
    def title(self) -> str:
        return self.conversation.title if self.conversation else NEW_CONVERSATION_TITLE

    def history_payload(self) -> List[Dict[str, Any]]:
        if not self.conversation or not self.settings.include_history:
            return []
        return self.conversation.history(self.settings.history_extra_fields)

    # ------------------------------------------------------------------ #
    # Startup: load (at most) one existing conversation
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        """Load the most recent Grace conversation, or prepare a fresh one.

        Exactly one conversation is ever adopted.  When the account has
        several, the most recently updated one wins - the same ordering the
        Aero web client's "Recents" list uses.
        """
        self._emit(Event(LOADING, "Loading your Grace conversation"))
        chats: List[ChatSummary] = []
        try:
            chats = self.client.load_chats()
        except AeroError as exc:
            log.info("grace history unavailable: %s", exc.code)
            self._emit(Event(ERROR, exc))

        chosen = _newest_chat(chats)
        if chosen is not None:
            conversation = conversation_from_chat(chosen, NEW_CONVERSATION_TITLE)
            log.info(
                "restored conversation %s with %d messages",
                _short(conversation.id),
                len(conversation.messages),
            )
            self.conversation = conversation
            self._emit(Event(CONVERSATION_READY, conversation))
            self._emit(Event(HISTORY_RESTORED, conversation))
        else:
            conversation = Conversation(id=new_id("gc_"))
            self.conversation = conversation
            self._emit(Event(CONVERSATION_READY, conversation))

        if self.client.user is not None:
            self._emit(Event(CONNECTION, self.client.user))

    # ------------------------------------------------------------------ #
    # Mode selection
    # ------------------------------------------------------------------ #
    def set_mode(self, key: str) -> GraceMode:
        self.mode = modes.get(key)
        self._emit(Event(MODE_CHANGED, self.mode))
        return self.mode

    # ------------------------------------------------------------------ #
    # Attachments
    # ------------------------------------------------------------------ #
    def _upload_attachment(self, path: str, on_progress: Callable[[float], None]):
        try:
            return self.client.upload_attachment(path, on_progress=on_progress)
        except AeroError as exc:
            raise AttachmentUploadFailed(str(exc)) from exc

    def add_attachments(self, paths: List[str]) -> List[str]:
        """Validate + queue files.  Returns human-readable problems."""
        added, problems = self.attachments.add_paths(paths)
        for problem in problems:
            log.debug("attachment rejected: %s", problem)
        if added:
            self._emit(Event(ATTACHMENT_CHANGED, None))
        return problems

    def remove_attachment(self, attachment_id: str) -> None:
        self.attachments.remove(attachment_id)
        self._emit(Event(ATTACHMENT_CHANGED, None))

    def retry_attachment(self, attachment_id: str) -> None:
        threading.Thread(
            target=self.attachments.retry, args=(attachment_id,), daemon=True
        ).start()

    def upload_attachments(self) -> None:
        self.attachments.upload_all()

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #
    def can_send(self, text: str) -> bool:
        if self._busy:
            return False
        if not text or not text.strip():
            return False
        if self.conversation is None:
            return False
        return True

    def send(self, text: str) -> bool:
        """Queue a message.  Returns ``False`` when it was rejected."""
        if not self.can_send(text):
            if self._busy:
                log.debug("send rejected: a response is already streaming")
            return False

        with self._send_lock:
            if self._busy:
                return False
            self._busy = True
            self._generation += 1
            generation = self._generation
            self._cancel.clear()

        self._emit(Event(BUSY, True))

        if self.attachments:
            self.attachments.upload_all()
            if self.attachments.any_failed:
                self._busy = False
                self._emit(Event(BUSY, False))
                self._emit(
                    Event(
                        ERROR,
                        AttachmentUploadFailed(
                            "Some files could not be uploaded. "
                            "Retry or remove them before sending."
                        ),
                    )
                )
                return False

        worker = threading.Thread(
            target=self._run,
            args=(text, generation),
            name=f"grace-send-{generation}",
            daemon=True,
        )
        self._worker = worker
        worker.start()
        return True

    def stop(self) -> None:
        """Cancel the in-flight generation, keeping the partial answer."""
        if not self._busy:
            return
        self._cancel.set()
        self._emit(Event(STATUS, "Stopping…"))

    def shutdown(self) -> None:
        self._cancel.set()
        self._emit(Event(SHUTDOWN, None))

    def reset(self) -> None:
        """Drop all in-memory conversation state (used on sign-out)."""
        self._cancel.set()
        self._busy = False
        self._generation += 1
        self._active_message = None
        self.conversation = None
        self.credits = Credits()
        self.attachments.clear()

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    def _run(self, text: str, generation: int) -> None:
        error: Optional[AeroError] = None
        try:
            self._run_inner(text, generation)
        except AeroError as exc:
            error = exc
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("unexpected failure while sending")
            error = AeroError(type(exc).__name__)
        finally:
            self._busy = False
            if error is not None and generation == self._generation:
                message = self._active_message
                if message is not None:
                    message.streaming = False
                    message.error = True
                    self._emit(Event(ASSISTANT_ERROR, message))
                    self._emit(Event(ERROR, error))
            self._active_message = None
            self._emit(Event(BUSY, False))

    def _run_inner(self, text: str, generation: int) -> None:
        assert self.conversation is not None
        conversation = self.conversation
        body = text.strip()

        user_message = Message(
            id=new_id("m_"),
            role=ROLE_USER,
            content=body,
            attachments=self.attachments.items,
        )
        conversation.messages.append(user_message)
        conversation.updated_at = now_iso()
        self._emit(Event(USER_MESSAGE, user_message))

        # The payload is built *before* the assistant placeholder exists so
        # the history we transmit never contains an empty assistant turn.
        payload = self._build_payload(body)

        assistant_message = Message(
            id=new_id("m_"), role=ROLE_ASSISTANT, content="", streaming=True
        )
        conversation.messages.append(assistant_message)
        self._active_message = assistant_message
        self._emit(Event(ASSISTANT_START, assistant_message))

        self._status = "Grace is thinking…"
        self._emit(Event(STATUS, self._status))

        result = self._stream(payload, assistant_message, generation)

        # ---- done / reconcile -------------------------------------- #
        if result.full_content:
            assistant_message.content = result.full_content
        assistant_message.streaming = False
        assistant_message.meta = {
            "tier": result.tier,
            "thinking": result.thinking,
            "effort": result.effort,
            "usedCredits": result.credits_used,
            "remainingCredits": result.remaining_credits,
            "updatedAt": result.extra.get("updatedAt", ""),
        }
        conversation.updated_at = (
            str(result.extra.get("updatedAt") or "") or conversation.updated_at
        )
        if result.conversation_id and result.conversation_id != conversation.id:
            log.info(
                "server renamed conversation %s -> %s",
                _short(conversation.id),
                _short(result.conversation_id),
            )
            conversation.id = result.conversation_id
            conversation.origin = "server"

        self._emit(Event(ASSISTANT_DONE, (assistant_message, result)))

        self._apply_credits(result)
        if result.statuses:
            self._status = ""
            self._emit(Event(STATUS, ""))

        # ---- title ------------------------------------------------- #
        if not conversation.title_generated and conversation.user_messages:
            self._maybe_generate_title(conversation)

        # ---- attachments ------------------------------------------- #
        self.attachments.clear()
        self._emit(Event(ATTACHMENTS_CLEARED, None))

    def _build_payload(self, body: str) -> Dict[str, Any]:
        conversation = self.conversation
        assert conversation is not None
        payload: Dict[str, Any] = {
            "message": body,
            "conversationHistory": self.history_payload(),
            "conversationId": conversation.id,
            "clientMessageId": new_id("m_"),
            "capabilities": list(config.DEFAULT_CAPABILITIES),
        }
        payload.update(self.mode.payload())

        references = self.attachments.ready_references()
        if references and self.settings.send_attachments:
            payload[config.PATH_GRACE_ATTACH_FIELD] = references
        return payload

    def _stream(
        self, payload: Dict[str, Any], assistant_message: Message, generation: int
    ) -> StreamResult:
        """Stream one answer, retrying once in Normal mode if it is refused."""
        try:
            return self._stream_once(payload, assistant_message, generation)
        except AeroError as exc:
            if self.mode.verified or not _looks_like_mode_error(exc):
                raise
            fallback = dict(payload)
            fallback.update(modes.default().payload())
            log.info("mode %s refused by server, retrying in Normal", self.mode.key)
            self._emit(
                Event(STATUS, f"{self.mode.label} is unavailable — using Normal.")
            )
            self.set_mode(modes.default().key)
            return self._stream_once(fallback, assistant_message, generation)

    def _stream_once(
        self, payload: Dict[str, Any], assistant_message: Message, generation: int
    ) -> StreamResult:
        result = StreamResult()
        collected: List[str] = []

        def _on_event(event) -> None:
            if generation != self._generation:
                return
            if event.is_done:
                result.statuses.append("[DONE]")
                return
            data = event.json()
            if not isinstance(data, dict):
                return
            kind = data.get("type")
            if kind == "chunk":
                piece = data.get("content")
                if isinstance(piece, str) and piece:
                    collected.append(piece)
                    assistant_message.content = "".join(collected)
                    result.full_content = assistant_message.content
                    self._emit(Event(ASSISTANT_CHUNK, assistant_message))
            elif kind == "status":
                label = data.get("content")
                if isinstance(label, str) and label:
                    result.statuses.append(label)
                    self._status = label
                    self._emit(Event(STATUS, label))
            elif kind == "done":
                _absorb_done(data, result)

        _, parser = self.client.respond_stream(
            payload, on_event=_on_event, cancel_event=self._cancel
        )
        if self._cancel.is_set():
            assistant_message.streaming = False
            self._status = ""
            self._emit(Event(STATUS, "Stopped"))

        if parser.stats.truncated and not self._cancel.is_set():
            # The stream ended without ``[DONE]``.
            raise GraceInterrupted("stream ended before [DONE]")

        # The streamed text is only a fallback: ``fullContent`` from the
        # ``done`` event is authoritative.
        if not result.full_content:
            result.full_content = assistant_message.content
        return result

    # ------------------------------------------------------------------ #
    def _apply_credits(self, result: StreamResult) -> None:
        if result.remaining_credits is None and result.credits_used is None:
            return
        self.credits = Credits(
            remaining=result.remaining_credits,
            used=result.credits_used,
            tier=result.tier,
            thinking=result.thinking,
            effort=result.effort,
        )
        self._emit(Event(CREDITS, self.credits))

    def _maybe_generate_title(self, conversation: Conversation) -> None:
        first = conversation.user_messages[0]
        if not first.content:
            return
        try:
            title = self.client.generate_title(first.content[:4000])
        except AeroError as exc:
            log.info("title generation failed: %s", exc.code)
            return
        title = (title or "").strip()
        if not title or title.lower() in ("new", "new conversation", "untitled"):
            return
        conversation.title = title[:80]
        conversation.title_generated = True
        self._emit(Event(TITLE, conversation.title))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _absorb_done(data: Dict[str, Any], result: StreamResult) -> None:
    full = data.get("fullContent")
    if isinstance(full, str) and full:
        result.full_content = full
    for key, attr in (
        ("usedCredits", "credits_used"),
        ("remainingCredits", "remaining_credits"),
    ):
        value = data.get(key)
        if isinstance(value, (int, float)):
            setattr(result, attr, float(value))
    for wire_key, attr in (
        ("tier", "tier"),
        ("effort", "effort"),
        ("conversationId", "conversation_id"),
        ("messageId", "message_id"),
    ):
        value = data.get(wire_key)
        if isinstance(value, str) and value:
            setattr(result, attr, value)
    thinking = data.get("thinking")
    if isinstance(thinking, bool):
        result.thinking = thinking
    result.extra.update(data)


def _newest_chat(chats: List[ChatSummary]) -> Optional[ChatSummary]:
    if not chats:
        return None
    return max(chats, key=lambda c: (c.updated_at or c.created_at or "", c.created_at))


def _short(value: str) -> str:
    return value[:8] + "…" if len(value) > 9 else value


_MODE_ERROR_MARKERS = ("mode", "effort", "tier")


def _looks_like_mode_error(exc: AeroError) -> bool:
    """Heuristic: did the server refuse the mode/effort pair we sent?"""
    haystack = f"{exc.detail} {exc.code}".lower()
    if not haystack.strip():
        return False
    if "mode" in haystack or "effort" in haystack or "tier" in haystack:
        return True
    return False
