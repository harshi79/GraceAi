"""Controller rules: one conversation, duplicate-send protection, streaming,
reconciliation with fullContent, credits, titles, mode fallback and errors."""

from __future__ import annotations

import threading
import time

import pytest

from grace import config
from grace.controller import (
    ASSISTANT_DONE,
    ASSISTANT_START,
    BUSY,
    CREDITS,
    ERROR,
    HISTORY_RESTORED,
    STATUS,
    TITLE,
    USER_MESSAGE,
    GraceController,
)
from grace.errors import GraceServerError


@pytest.fixture()
def controller(authed):
    events = []
    ctrl = GraceController(authed, on_event=events.append)
    ctrl.events = events  # type: ignore[attr-defined]
    return ctrl


@pytest.fixture()
def empty_controller(controller):
    """Controller with no server-side history (a fresh conversation)."""
    controller.client.load_chats = lambda: []
    controller.bootstrap()
    controller.events.clear()
    return controller


def kinds(events):
    return [e.kind for e in events]


# --------------------------------------------------------------------------- #
# One conversation per client session
# --------------------------------------------------------------------------- #

def test_bootstrap_adopts_the_most_recent_conversation(controller):
    controller.bootstrap()
    assert controller.conversation is not None
    assert controller.conversation.id == "gc_server_1"
    assert controller.conversation.title == "Debug the render loop"
    assert len(controller.conversation.messages) == 2
    assert HISTORY_RESTORED in kinds(controller.events)


def test_bootstrap_with_no_chats_creates_one_local_conversation(controller):
    controller.client.load_chats = lambda: []
    controller.bootstrap()
    assert controller.conversation.id.startswith("gc_")
    assert controller.conversation.messages == []
    assert HISTORY_RESTORED not in kinds(controller.events)


def test_bootstrap_survives_a_chats_failure(controller):
    from grace.errors import AuthFailure

    controller.client.load_chats = lambda: (_ for _ in ()).throw(AuthFailure("no"))
    controller.bootstrap()
    assert controller.conversation is not None
    assert ERROR in kinds(controller.events)


def test_only_one_conversation_is_ever_created(controller):
    controller.bootstrap()
    first = controller.conversation.id
    controller.bootstrap()
    assert controller.conversation.id == first


def test_no_new_chat_api_is_exposed(controller):
    """The client must not offer a 'new conversation' action."""
    assert not hasattr(controller, "new_conversation")
    assert not hasattr(controller, "new_chat")
    assert not hasattr(controller, "create_conversation")


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #

def test_empty_message_is_refused(controller):
    controller.bootstrap()
    assert controller.send("") is False
    assert controller.send("   \n\t ") is False
    assert USER_MESSAGE not in kinds(controller.events)


def test_duplicate_send_is_refused_while_streaming(empty_controller, authed):
    controller = empty_controller
    release = threading.Event()
    authed.respond_stream = _gated_stream(release)
    assert controller.send("first") is True
    assert controller.busy is True
    assert controller.send("second") is False
    assert controller.send("third") is False
    assert len(controller.conversation.user_messages) == 1
    release.set()
    _wait_idle(controller)


def test_concurrent_send_from_many_threads_yields_one_message(empty_controller, authed):
    controller = empty_controller
    release = threading.Event()
    authed.respond_stream = _gated_stream(release)
    results = []
    barrier = threading.Barrier(8)

    def attempt(i):
        barrier.wait(timeout=10)
        results.append(controller.send(f"msg {i}"))

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for r in results if r) == 1
    assert len(controller.conversation.user_messages) == 1
    release.set()
    _wait_idle(controller)


def test_send_emits_user_then_assistant_then_done(controller):
    controller.bootstrap()
    controller.send("hello")
    _wait_idle(controller)
    order = [k for k in kinds(controller.events)
             if k in (USER_MESSAGE, ASSISTANT_START, ASSISTANT_DONE)]
    assert order == [USER_MESSAGE, ASSISTANT_START, ASSISTANT_DONE]


def test_streaming_updates_accumulate(controller):
    controller.bootstrap()
    controller.send("hello")
    _wait_idle(controller)
    assistant = controller.conversation.messages[-1]
    assert assistant.content == "Hello there."
    assert assistant.streaming is False
    assert assistant.meta["tier"] == "normal"
    assert assistant.meta["thinking"] is False
    assert assistant.meta["usedCredits"] == 1.25


def test_full_content_replaces_streamed_text(controller, authed):
    controller.bootstrap()
    # Stream says "PARTIAL", but the done event carries the authoritative text.
    authed.set_respond_events = None
    controller.client.respond_stream = _stream_with(
        [
            {"type": "chunk", "content": "PART"},
            {"type": "chunk", "content": "IAL"},
            {"type": "done", "fullContent": "THE WHOLE ANSWER",
             "remainingCredits": 10.0, "tier": "ultra", "thinking": True,
             "effort": "thinking", "usedCredits": 2.0},
        ]
    )
    controller.send("hello")
    _wait_idle(controller)
    assistant = controller.conversation.messages[-1]
    assert assistant.content == "THE WHOLE ANSWER"


def test_status_events_are_forwarded(controller):
    controller.bootstrap()
    controller.send("hello")
    _wait_idle(controller)
    assert STATUS in kinds(controller.events)


def test_credits_are_taken_from_the_done_event(controller):
    controller.bootstrap()
    controller.send("hello")
    _wait_idle(controller)
    assert controller.credits.remaining == 141.5
    assert controller.credits.used == 1.25
    assert controller.credits.tier == "normal"
    assert CREDITS in kinds(controller.events)


def test_title_is_generated_once(empty_controller):
    controller = empty_controller
    controller.send("hello")
    _wait_idle(controller)
    assert controller.title == "Debug the render loop"
    assert TITLE in kinds(controller.events)
    # A second turn must not regenerate it.
    before = len(controller.events)
    controller.send("again")
    _wait_idle(controller)
    assert TITLE not in kinds(controller.events[before:])


def test_title_is_kept_when_server_returns_new(empty_controller):
    controller = empty_controller
    controller.client.generate_title = lambda m: "New"
    controller.send("hello")
    _wait_idle(controller)
    assert controller.title == "New conversation"
    assert controller.conversation.title_generated is False


def test_title_failure_is_not_fatal(empty_controller):
    from grace.errors import GraceServerError

    controller = empty_controller
    controller.client.generate_title = lambda m: (_ for _ in ()).throw(
        GraceServerError("nope")
    )
    controller.send("hello")
    _wait_idle(controller)
    assert controller.title == "New conversation"
    assert controller.conversation.messages[-1].content == "Hello there."


def test_history_contains_every_prior_turn(controller):
    controller.bootstrap()
    controller.send("first question")
    _wait_idle(controller)
    history = controller.history_payload()
    assert [h["role"] for h in history] == ["user", "assistant", "user", "assistant"]
    assert history[-2]["content"] == "first question"
    assert history[-1]["content"] == "Hello there."


def test_history_is_rebuilt_from_the_conversation(controller):
    controller.bootstrap()
    controller.send("q1")
    _wait_idle(controller)
    # Ask twice: the payload must always be regenerated from live state, so a
    # stale snapshot can never be transmitted.
    first = controller._build_payload("q2")
    second = controller._build_payload("q3")
    assert first["conversationHistory"] == second["conversationHistory"]
    assert first["conversationHistory"][-2]["content"] == "q1"
    assert first["conversationHistory"][-1]["content"] == "Hello there."
    assert first["message"] == "q2"
    assert second["message"] == "q3"
    # Mutating the returned payload must not corrupt the conversation.
    first["conversationHistory"].append({"role": "user", "content": "injected"})
    assert controller.conversation.messages[-1].content == "Hello there."


def test_payload_shape(controller):
    controller.bootstrap()
    controller.send("hello")
    _wait_idle(controller)
    payload = controller._build_payload("hello again")
    assert payload["message"] == "hello again"
    assert payload["mode"] == "normal"
    assert payload["effort"] == "instant"
    assert payload["conversationId"] == "gc_server_1"
    assert payload["capabilities"] == list(config.DEFAULT_CAPABILITIES)
    assert payload["clientMessageId"]
    assert "conversationHistory" in payload


def test_attachments_are_referenced_in_the_payload(controller, authed, tmp_path):
    controller.bootstrap()
    path = tmp_path / "a.txt"
    path.write_text("data")
    controller.add_attachments([str(path)])
    controller.upload_attachments()
    assert controller.attachments.all_ready
    payload = controller._build_payload("summarise this")
    assert payload[config.PATH_GRACE_ATTACH_FIELD] == ["f_a.txt"]
    # ...and they are cleared after a successful turn.
    controller.send("summarise this")
    _wait_idle(controller)
    assert controller.attachments.items == []


def test_attachments_can_be_disabled(controller, tmp_path):
    controller.bootstrap()
    controller.settings.send_attachments = False
    path = tmp_path / "a.txt"
    path.write_text("data")
    controller.add_attachments([str(path)])
    controller.upload_attachments()
    payload = controller._build_payload("x")
    assert config.PATH_GRACE_ATTACH_FIELD not in payload


# --------------------------------------------------------------------------- #
# Failure modes
# --------------------------------------------------------------------------- #

def test_server_error_is_surfaced_and_state_restored(controller):
    from grace.errors import GraceServerError

    controller.bootstrap()
    controller.client.respond_stream = _raising(GraceServerError("Grace exploded"))
    assert controller.send("hello") is True
    _wait_idle(controller)
    assert controller.busy is False
    assert ERROR in kinds(controller.events)
    assert controller.conversation.messages[-1].error is True


def test_mode_rejection_falls_back_to_normal(controller, authed):
    controller.bootstrap()
    controller.set_mode("ultra-thinking")
    calls = []

    def flaky(payload, on_event=None, cancel_event=None):
        calls.append(dict(payload))
        if payload["mode"] != "normal":
            raise GraceServerError('mode "ultra" is not enabled for this account')
        return authed.__class__.respond_stream(
            authed, payload, on_event=on_event, cancel_event=cancel_event
        )

    authed.respond_stream = flaky
    controller.send("hello")
    _wait_idle(controller)
    assert len(calls) == 2
    assert calls[0]["mode"] == "ultra"
    assert calls[1]["mode"] == "normal"
    assert controller.mode.verified is True
    assert controller.conversation.messages[-1].content == "Hello there."


def test_verified_mode_is_not_retried(controller, authed):
    controller.bootstrap()
    calls = []

    def always_fail(payload, on_event=None, cancel_event=None):
        calls.append(payload)
        raise GraceServerError("mode normal is broken")

    authed.respond_stream = always_fail
    controller.send("hello")
    _wait_idle(controller)
    assert len(calls) == 1


def test_cancel_keeps_partial_answer(controller, authed):
    controller.bootstrap()
    def cancelling(payload, on_event=None, cancel_event=None):
        on_event(_evt({"type": "chunk", "content": "half "}))
        cancel_event.set()
        on_event(_evt({"type": "chunk", "content": "answer"}))
        from grace.sse import SSEParser

        return [], SSEParser()

    authed.respond_stream = cancelling
    controller.send("hello")
    _wait_idle(controller)
    assistant = controller.conversation.messages[-1]
    assert assistant.content == "half answer"
    assert assistant.streaming is False


def test_busy_events_are_emitted(controller):
    controller.bootstrap()
    controller.send("hello")
    _wait_idle(controller)
    assert BUSY in kinds(controller.events)


def test_stop_is_a_noop_when_idle(controller):
    controller.bootstrap()
    controller.stop()  # must not raise
    assert controller.busy is False


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #

def test_set_mode_emits_event(controller):
    controller.set_mode("ultra-thinking")
    assert controller.mode.key == "ultra-thinking"
    assert controller.mode.payload() == {"mode": "ultra", "effort": "thinking"}


def test_unknown_mode_falls_back_to_normal(controller):
    controller.set_mode("does-not-exist")
    assert controller.mode.key == "normal"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _Evt:
    """Mirrors ``grace.sse.SSEEvent``: only the literal ``[DONE]`` sentinel
    sets ``is_done``; a ``{"type": "done"}`` frame is ordinary JSON."""

    def __init__(self, payload, done=False):
        self._payload = payload
        self._done = done

    @property
    def is_done(self):
        return self._done

    def json(self):
        return None if self._done else self._payload


def _evt(payload, done=False):
    return _Evt(payload, done=done)


def _stream_with(events, sentinel=True):
    def run(payload, on_event=None, cancel_event=None):
        for event in events:
            on_event(_evt(event))
        if sentinel:
            on_event(_evt(None, done=True))
        from grace.sse import SSEParser

        parser = SSEParser()
        parser.stats.done = True
        return [], parser

    return run


def _gated_stream(release, timeout: float = 10.0):
    """A stream that stays open until the test releases it."""

    def run(payload, on_event=None, cancel_event=None):
        release.wait(timeout)
        on_event(_evt({"type": "chunk", "content": "ok"}))
        on_event(_evt(None, done=True))
        from grace.sse import SSEParser

        parser = SSEParser()
        parser.stats.done = True
        return [], parser

    return run


def _raising(exc):
    def run(payload, on_event=None, cancel_event=None):
        raise exc

    return run


def _wait_idle(controller, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not controller.busy:
            time.sleep(0.02)
            return
        time.sleep(0.01)
    raise AssertionError("controller never became idle")
