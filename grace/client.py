"""HTTP client for the Aero REST API.

Design notes
------------
* **HTTPS only.**  The base origin is hard-coded to ``https://`` and any
  attempt to point it at ``http://`` is rejected at import time.
* **Credentials live in memory only.**  The token is held on the
  ``requests.Session`` object, never written anywhere, and never logged.
* **Injectable transport.**  Tests pass a ``base_url`` pointing at a local
  mock server and (optionally) a pre-built session, so no test ever touches
  the network.
* **Tolerant response parsing.**  Where a response shape could not be
  verified from the live API the parser accepts several plausible layouts and
  records which one matched, instead of guessing a single one.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from . import config
from .errors import (
    AeroError,
    AuthFailure,
    GraceServerError,
    InvalidCredentials,
    OtpRejected,
    from_exception,
    from_http_status,
)
from .logutil import log
from .models import (
    Attachment,
    Conversation,
    Message,
    ROLE_ASSISTANT,
    ROLE_USER,
    User,
    new_id,
    now_iso,
)
from .sse import SSEEvent, SSEParser

# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #


@dataclass
class LoginOutcome:
    status: str  # "ok" | "otp_required"
    access_token: str = ""
    user: Optional[User] = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok" and bool(self.access_token)


@dataclass
class ChatSummary:
    """One conversation as returned by ``GET /api/ai/grace/chats``."""

    id: str
    title: str = ""
    updated_at: str = ""
    created_at: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    messages: List[Dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _first_key(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _error_from_body(status: int, body: str) -> AeroError:
    """Turn an error response into the closest taxonomy member."""
    message = ""
    code = ""
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        parsed = {}
    if isinstance(parsed, dict):
        message = str(parsed.get("message") or parsed.get("error") or "")
        code = str(parsed.get("code") or "")
        errors = parsed.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = str(first.get("message") or first.get("msg") or message)
            else:
                message = str(first)
    if status in (401, 403):
        if code == "NO_TOKEN" or not message:
            return AuthFailure(code or "missing token", status=status)
        return InvalidCredentials(message, status=status)
    return from_http_status(status, message or body)


def parse_chat_list(payload: Any) -> List[ChatSummary]:
    """Normalise the several shapes ``/ai/grace/chats`` could return.

    Accepted: a bare list, ``{"chats": [...]}``, ``{"conversations": [...]}``,
    ``{"data": [...]}`` and ``{"chats": {"docs": [...]}}``.
    """
    items: Any = payload
    if isinstance(payload, dict):
        for key in ("chats", "conversations", "data", "items", "results"):
            if key in payload:
                items = payload[key]
                break
        else:
            items = []
    if isinstance(items, dict):
        for key in ("docs", "items", "results", "data"):
            if key in items and isinstance(items[key], list):
                items = items[key]
                break
        else:
            items = []
    if not isinstance(items, list):
        return []

    out: List[ChatSummary] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        chat_id = str(_first_key(item, "_id", "id", "conversationId", "chatId") or "")
        if not chat_id:
            continue
        title = str(_first_key(item, "title", "name", "subject") or "")
        updated = str(
            _first_key(item, "updatedAt", "lastMessageAt", "updated_at", "createdAt")
            or ""
        )
        created = str(_first_key(item, "createdAt", "created_at", "updatedAt") or "")
        raw_messages = _first_key(item, "messages", "history", "turns") or []
        messages = [m for m in raw_messages if isinstance(m, dict)]
        out.append(
            ChatSummary(
                id=chat_id,
                title=title,
                updated_at=updated,
                created_at=created,
                raw=item,
                messages=messages,
            )
        )
    return out


def conversation_from_chat(chat: ChatSummary, fallback_title: str) -> Conversation:
    """Rebuild a :class:`Conversation` (with messages) from a chat summary."""
    convo = Conversation(
        id=chat.id,
        title=chat.title or fallback_title,
        created_at=chat.created_at or now_iso(),
        updated_at=chat.updated_at or chat.created_at or now_iso(),
        origin="server",
        title_generated=bool(chat.title),
    )
    for raw in chat.messages:
        role = str(_first_key(raw, "role", "sender", "author") or "").lower()
        if role in ("user", "human"):
            role = ROLE_USER
        elif role in ("assistant", "grace", "ai", "bot", "model"):
            role = ROLE_ASSISTANT
        else:
            continue
        content = _first_key(raw, "content", "text", "message", "body")
        if content is None:
            continue
        if isinstance(content, list):  # [{type:"text", text:"..."}] blocks
            content = "".join(
                str(b.get("text", "")) for b in content if isinstance(b, dict)
            )
        msg = Message(
            id=str(_first_key(raw, "_id", "id", "messageId") or new_id("m_")),
            role=role,
            content=str(content),
            at=str(_first_key(raw, "createdAt", "at", "timestamp") or now_iso()),
        )
        meta = _first_key(raw, "meta", "metadata")
        if isinstance(meta, dict):
            msg.meta = meta
        convo.messages.append(msg)
    return convo


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


class AeroClient:
    """Thin, auditable wrapper around the Aero REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
    ) -> None:
        origin = (base_url or config.API_ORIGIN).rstrip("/")
        if origin.startswith("http://") and not origin.startswith("http://127."):
            # Only a loopback test double may speak plaintext.
            raise ValueError("Refusing to use a non-HTTPS Aero endpoint")
        self.origin = origin
        self.connect_timeout = connect_timeout or config.CONNECT_TIMEOUT
        self.read_timeout = read_timeout or config.READ_TIMEOUT
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/event-stream, */*",
            }
        )
        self.access_token: str = ""
        self.user: Optional[User] = None
        #: Which chats-list layout the server actually used.
        self.chats_layout: str = ""

    # ------------------------------------------------------------------ #
    # Session / auth
    # ------------------------------------------------------------------ #
    def set_token(self, token: str) -> None:
        """Install the bearer token.  Memory only, never logged or stored."""
        self.access_token = token
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers.pop("Authorization", None)

    def clear_token(self) -> None:
        self.set_token("")
        self.user = None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    def _endpoint(self, path: str) -> str:
        return f"{self.origin}{config.API_PREFIX}{path}"

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    def login(self, identifier: str, password: str) -> LoginOutcome:
        """``POST /api/auth/login`` with ``{identifier, password}``."""
        url = self._endpoint(config.PATH_AUTH_LOGIN)
        try:
            response = self.session.post(
                url,
                json={"identifier": identifier, "password": password},
                timeout=(self.connect_timeout, 30),
            )
        except requests.RequestException as exc:
            raise from_exception(exc) from exc

        if response.status_code in (400, 401, 403):
            raise _error_from_body(response.status_code, response.text)

        try:
            data = response.json()
        except ValueError:
            raise GraceServerError(
                "Unexpected login response", status=response.status_code
            ) from None

        if not isinstance(data, dict):
            raise GraceServerError("Unexpected login response")

        token = _first_key(data, "accessToken", "token", "access_token", "jwt")
        if token:
            self.set_token(str(token))
            self.user = User.from_login(data)
            return LoginOutcome(status="ok", access_token=str(token), user=self.user)

        # A 200 with no token is the documented "OTP sent" branch.
        message = str(data.get("message") or "Verification code sent")
        self.access_token = ""
        return LoginOutcome(status="otp_required", message=message)

    def verify_otp(self, identifier: str, code: str) -> LoginOutcome:
        """Second leg of the OTP login challenge.

        The live endpoint could not be observed from this environment; see
        :data:`grace.config.PATH_AUTH_OTP_VERIFY`.
        """
        url = self._endpoint(config.PATH_AUTH_OTP_VERIFY)
        try:
            response = self.session.post(
                url,
                json={"identifier": identifier, "code": code},
                timeout=(self.connect_timeout, 30),
            )
        except requests.RequestException as exc:
            raise from_exception(exc) from exc

        if response.status_code in (400, 401, 403):
            raise OtpRejected(response.text, status=response.status_code)

        try:
            data = response.json()
        except ValueError:
            raise GraceServerError("Unexpected verification response") from None
        if not isinstance(data, dict):
            raise GraceServerError("Unexpected verification response")

        token = _first_key(data, "accessToken", "token", "access_token", "jwt")
        if not token:
            raise OtpRejected("No token returned")
        self.set_token(str(token))
        self.user = User.from_login(data)
        return LoginOutcome(status="ok", access_token=str(token), user=self.user)

    # ------------------------------------------------------------------ #
    # Grace conversations
    # ------------------------------------------------------------------ #
    def load_chats(self) -> List[ChatSummary]:
        """``GET /api/ai/grace/chats`` -> newest conversation first."""
        url = self._endpoint(config.PATH_GRACE_CHATS)
        try:
            response = self.session.get(url, timeout=(self.connect_timeout, 30))
        except requests.RequestException as exc:
            raise from_exception(exc) from exc

        if response.status_code in (401, 403):
            raise _error_from_body(response.status_code, response.text)
        if response.status_code >= 400:
            raise from_http_status(response.status_code, response.text)

        try:
            payload = response.json()
        except ValueError:
            raise GraceServerError("Grace history returned an unreadable response")

        if isinstance(payload, dict):
            for key in ("chats", "conversations", "data", "items", "results"):
                if isinstance(payload.get(key), list):
                    self.chats_layout = key
                    break
        else:
            self.chats_layout = "list"
        return parse_chat_list(payload)

    def generate_title(self, message: str) -> str:
        """``POST /api/ai/grace/generate-title`` with ``{message}``."""
        url = self._endpoint(config.PATH_GRACE_TITLE)
        try:
            response = self.session.post(
                url, json={"message": message}, timeout=(self.connect_timeout, 45)
            )
        except requests.RequestException as exc:
            raise from_exception(exc) from exc
        if response.status_code >= 400:
            raise from_http_status(response.status_code, response.text)
        try:
            data = response.json()
        except ValueError:
            raise GraceServerError("Title service returned an unreadable response")
        if isinstance(data, dict):
            title = _first_key(data, "title", "name")
            return str(title or "")
        return ""

    # ------------------------------------------------------------------ #
    # Grace streaming answer
    # ------------------------------------------------------------------ #
    def respond_stream(
        self,
        payload: Dict[str, Any],
        on_event: Optional[Callable[[SSEEvent], None]] = None,
        cancel_event: Optional["threading.Event"] = None,
    ) -> Tuple[List[SSEEvent], SSEParser]:
        """POST the answer request and collect every SSE event.

        Returns the collected events plus the parser (so the caller can read
        ``stats``).  Raises :class:`~grace.errors.AeroError` for transport and
        HTTP failures; a truncated stream is reported through
        ``parser.stats.truncated`` rather than an exception so the partial
        answer can still be shown.
        """
        url = self._endpoint(config.PATH_GRACE_RESPOND)
        parser = SSEParser()
        events: List[SSEEvent] = []

        def _emit(event: SSEEvent) -> None:
            events.append(event)
            if on_event is not None:
                on_event(event)

        try:
            response = self.session.post(
                url,
                json=payload,
                stream=True,
                timeout=(self.connect_timeout, self.read_timeout),
            )
        except requests.RequestException as exc:
            raise from_exception(exc) from exc

        try:
            if response.status_code >= 400:
                body = ""
                try:
                    body = response.text
                except Exception:  # pragma: no cover - defensive
                    body = ""
                raise from_http_status(response.status_code, body)

            content_type = (response.headers.get("Content-Type") or "").lower()
            if "text/event-stream" not in content_type and "text/plain" not in content_type:
                # A JSON error body can arrive with a 200 and no SSE headers.
                try:
                    body = response.text
                except Exception:  # pragma: no cover - defensive
                    body = ""
                if body.lstrip().startswith("{"):
                    raise from_http_status(response.status_code, body)
                # Fall back to treating it as a raw stream anyway.

            for raw in response.iter_content(chunk_size=4096):
                if cancel_event is not None and cancel_event.is_set():
                    parser.stats.truncated = True
                    return events, parser
                if not raw:
                    continue
                for event in parser.feed(raw):
                    _emit(event)
                    if event.is_done:
                        return events, parser
            for event in parser.flush():
                _emit(event)
                if event.is_done:
                    return events, parser
        except requests.RequestException as exc:
            # Interruption mid-stream: keep whatever arrived so far.
            parser.stats.truncated = True
            if not events:
                raise from_exception(exc) from exc
            log.warning("Grace stream interrupted after %d events", len(events))
        finally:
            try:
                response.close()
            except Exception:  # pragma: no cover - defensive
                pass

        if not parser.stats.done:
            parser.stats.truncated = True
        return events, parser

    # ------------------------------------------------------------------ #
    # Attachments
    # ------------------------------------------------------------------ #
    def upload_attachment(
        self,
        path: str,
        field_name: Optional[str] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> Attachment:
        """Multipart-upload ``path`` and return an :class:`Attachment`.

        The endpoint and field name are configurable because the browser's
        upload request could not be captured from this environment.
        """
        if not os.path.isfile(path):
            raise GraceServerError("Attachment is not a readable file")

        field = field_name or config.UPLOAD_FIELD
        url = self._endpoint(config.PATH_UPLOAD)
        name = os.path.basename(path)
        size = os.path.getsize(path)
        body = _ProgressFile(path, on_progress, size)

        attachment = Attachment(
            id=new_id("att_"),
            path=path,
            name=name,
            size=size,
            mime=_guess_mime(name),
            state="uploading",
        )

        try:
            response = self.session.post(
                url,
                files={field: (name, body, attachment.mime)},
                data={"name": name},
                timeout=(self.connect_timeout, max(120.0, self.read_timeout)),
            )
        except requests.RequestException as exc:
            attachment.state = "failed"
            attachment.error = "upload transport failed"
            raise from_exception(exc) from exc

        if response.status_code >= 400:
            attachment.state = "failed"
            attachment.error = f"HTTP {response.status_code}"
            raise from_http_status(response.status_code, response.text)

        try:
            data = response.json()
        except ValueError:
            data = {}

        remote = ""
        if isinstance(data, dict):
            remote = str(
                _first_key(
                    data,
                    "fileId",
                    "file_id",
                    "id",
                    "_id",
                    "attachmentId",
                    "key",
                    "url",
                )
                or ""
            )
            if not remote:
                inner = _first_key(data, "file", "attachment", "data")
                if isinstance(inner, dict):
                    remote = str(_first_key(inner, "_id", "id", "fileId", "url") or "")
        elif isinstance(data, str):
            remote = data

        attachment.state = "uploaded"
        attachment.remote_id = remote
        attachment.progress = 1.0
        return attachment


class _ProgressFile:
    """Read-only file wrapper that reports upload progress."""

    def __init__(self, path: str, on_progress, size: int) -> None:
        self._handle = open(path, "rb")
        self._on_progress = on_progress
        self._size = size
        self._sent = 0

    def read(self, size=-1):
        block = self._handle.read(size)
        if block:
            self._sent += len(block)
            if self._on_progress and self._size:
                self._on_progress(min(1.0, self._sent / self._size))
        return block

    def __len__(self):
        return self._size

    def close(self):
        try:
            self._handle.close()
        except Exception:  # pragma: no cover - defensive
            pass


def _guess_mime(name: str) -> str:
    import mimetypes

    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"
