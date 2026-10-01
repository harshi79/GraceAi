"""End-to-end flows against the contract-faithful mock Aero server.

These exercise the whole stack - HTTP client, SSE parser, controller state
machine and the payload it puts on the wire - without touching the network.
"""

from __future__ import annotations

import time

import pytest

from grace import config, modes
from grace.controller import GraceController
from grace.errors import AuthFailure


def make_controller(authed):
    events = []
    ctrl = GraceController(authed, on_event=events.append)
    ctrl.events = events  # type: ignore[attr-defined]
    return ctrl


def idle(ctrl, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ctrl.busy:
            time.sleep(0.02)
            return
        time.sleep(0.01)
    raise AssertionError("controller never became idle")


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #

def test_invalid_login_is_rejected_before_any_grace_call(client, state):
    with pytest.raises(AuthFailure):
        client.login("ada@example.com", "nope")
    assert state.respond_payloads == []


def test_unauthenticated_grace_calls_are_rejected(client):
    with pytest.raises(AuthFailure):
        client.load_chats()
    with pytest.raises(AuthFailure):
        client.generate_title("hi")
    with pytest.raises(AuthFailure):
        client.respond_stream({"message": "hi"})


# --------------------------------------------------------------------------- #
# Full conversation lifecycle
# --------------------------------------------------------------------------- #

def test_full_lifecycle(authed, state):
    ctrl = make_controller(authed)
    ctrl.bootstrap()

    # 1. the most recent server conversation is adopted, not a new one
    assert ctrl.conversation.id == "gc_server_1"
    assert len(ctrl.conversation.messages) == 2

    # 2. first turn
    assert ctrl.send("Why does my loop stutter?") is True
    idle(ctrl)

    payload = state.respond_payloads[-1]
    assert payload["message"] == "Why does my loop stutter?"
    assert payload["conversationId"] == "gc_server_1"
    assert payload["mode"] == "normal"
    assert payload["effort"] == "instant"
    assert payload["capabilities"] == list(config.DEFAULT_CAPABILITIES)
    assert [h["role"] for h in payload["conversationHistory"]] == [
        "user", "assistant", "user"
    ]
    assert payload["conversationHistory"][-1]["content"] == "Why does my loop stutter?"

    # 3. the answer is reconciled with fullContent
    assistant = ctrl.conversation.messages[-1]
    assert assistant.role == "assistant"
    assert assistant.content == "Hello there."
    assert assistant.streaming is False

    # 4. credits and title
    assert ctrl.credits.remaining == 141.5
    assert ctrl.credits.used == 1.25
    assert ctrl.title == "Debug the render loop"

    # 5. a second turn keeps the same conversation and grows the history
    assert ctrl.send("And the allocator?") is True
    idle(ctrl)
    assert len(state.respond_payloads) == 2
    payload = state.respond_payloads[-1]
    assert payload["conversationId"] == "gc_server_1"
    assert [h["role"] for h in payload["conversationHistory"]] == [
        "user", "assistant", "user", "assistant", "user"
    ]
    assert len(ctrl.conversation.messages) == 6

    # 6. exactly one conversation exists for this session
    assert ctrl.conversation.id == "gc_server_1"


def test_fresh_account_uses_one_client_generated_conversation(authed, state):
    state.chats = []
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    first_id = ctrl.conversation.id
    assert first_id.startswith("gc_")

    ctrl.send("hello")
    idle(ctrl)
    assert state.respond_payloads[-1]["conversationId"] == first_id
    assert ctrl.conversation.id == first_id
    assert len(state.respond_payloads) == 1


def test_server_supplied_conversation_id_is_adopted(authed, state):
    state.set_respond_events(
        [
            {"type": "chunk", "content": "hi"},
            {"type": "done", "fullContent": "hi", "conversationId": "gc_canonical",
             "remainingCredits": 3.0, "tier": "normal", "effort": "instant",
             "thinking": False, "updatedAt": "2026-06-03T10:00:00Z"},
        ]
    )
    state.chats = []
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.send("hello")
    idle(ctrl)
    assert ctrl.conversation.id == "gc_canonical"
    assert ctrl.conversation.origin == "server"
    assert ctrl.conversation.updated_at == "2026-06-03T10:00:00Z"


# --------------------------------------------------------------------------- #
# Streaming realism
# --------------------------------------------------------------------------- #

def test_long_answer_streams_in_many_chunks(authed, state):
    words = [f"w{i}" for i in range(500)]
    state.set_respond_events(
        [{"type": "chunk", "content": w + " "} for w in words]
        + [{"type": "done", "fullContent": " ".join(words),
            "remainingCredits": 1.0, "tier": "normal", "effort": "instant",
            "thinking": False}]
    )
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.send("write a lot")
    idle(ctrl)
    assert ctrl.conversation.messages[-1].content == " ".join(words)


def test_malformed_events_do_not_break_the_stream(authed, state, monkeypatch):
    """A garbage frame between good ones must be ignored, not fatal."""
    original = authed.respond_stream

    def patched(payload, on_event=None, cancel_event=None):
        from grace.sse import SSEEvent

        events = [
            SSEEvent(data='{"type":"status","content":"thinking"}'),
            SSEEvent(data="this is not json"),
            SSEEvent(data='{"type":"chunk","content":"ok"}'),
            SSEEvent(data="[DONE]"),
        ]
        for event in events:
            on_event(event)
        from grace.sse import SSEParser

        parser = SSEParser()
        parser.stats.done = True
        return events, parser

    authed.respond_stream = patched
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.send("hello")
    idle(ctrl)
    assert ctrl.conversation.messages[-1].content == "ok"
    authed.respond_stream = original


def test_server_error_leaves_a_usable_conversation(authed, state):
    state.fail_with(500, {"message": "Grace is unavailable"})
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.send("hello")
    idle(ctrl)
    assert ctrl.busy is False
    assert ctrl.conversation.messages[-1].error is True
    # the composer is re-enabled and the user can try again
    assert ctrl.send("try again") is True
    idle(ctrl)


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("mode", list(modes.ALL_MODES), ids=lambda m: m.key)
def test_every_mode_is_sent_and_echoed(authed, state, mode):
    state.set_respond_events(
        [
            {"type": "chunk", "content": "answer"},
            {"type": "done", "fullContent": "answer", "tier": mode.mode,
             "effort": mode.effort, "thinking": mode.thinking,
             "remainingCredits": 5.0, "usedCredits": 1.0},
        ]
    )
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.set_mode(mode.key)
    ctrl.send("hello")
    idle(ctrl)
    payload = state.respond_payloads[-1]
    assert payload["mode"] == mode.mode
    assert payload["effort"] == mode.effort
    assert payload["capabilities"] == list(config.DEFAULT_CAPABILITIES)
    assistant = ctrl.conversation.messages[-1]
    assert assistant.meta["tier"] == mode.mode
    assert assistant.meta["thinking"] == mode.thinking
    assert assistant.meta["effort"] == mode.effort


def test_mode_echo_mismatch_is_visible_in_the_message_metadata(authed, state):
    """If the server answers in a different tier, the turn records it."""
    state.set_respond_events(
        [
            {"type": "chunk", "content": "a"},
            {"type": "done", "fullContent": "a", "tier": "ultra",
             "effort": "thinking", "thinking": True, "remainingCredits": 1.0},
        ]
    )
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.send("hello")
    idle(ctrl)
    meta = ctrl.conversation.messages[-1].meta
    assert (meta["tier"], meta["effort"], meta["thinking"]) == ("ultra", "thinking", True)


# --------------------------------------------------------------------------- #
# Attachments
# --------------------------------------------------------------------------- #

def test_attachment_round_trip(authed, state, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("some context for Grace")
    ctrl = make_controller(authed)
    ctrl.bootstrap()

    problems = ctrl.add_attachments([str(path)])
    assert problems == []
    ctrl.upload_attachments()
    assert ctrl.attachments.all_ready

    ctrl.send("summarise the attachment")
    idle(ctrl)
    payload = state.respond_payloads[-1]
    assert payload[config.PATH_GRACE_ATTACH_FIELD] == ["f_notes.txt"]
    assert state.uploads[0]["name"] == "notes.txt"
    assert ctrl.attachments.items == []


def test_failed_attachment_blocks_sending(authed, state, tmp_path):
    state.upload_status = 500
    path = tmp_path / "notes.txt"
    path.write_text("data")
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.add_attachments([str(path)])
    ctrl.upload_attachments()
    assert ctrl.attachments.any_failed
    assert ctrl.send("hello") is False
    assert state.respond_payloads == []


def test_unsupported_attachment_is_refused(authed, tmp_path):
    path = tmp_path / "payload.exe"
    path.write_bytes(b"MZ")
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    problems = ctrl.add_attachments([str(path)])
    assert problems
    assert ctrl.attachments.items == []


# --------------------------------------------------------------------------- #
# Interruption
# --------------------------------------------------------------------------- #

def test_connection_drop_mid_stream_keeps_the_partial_answer(authed, state, monkeypatch):
    from grace.sse import SSEEvent

    def dropping(payload, on_event=None, cancel_event=None):
        on_event(SSEEvent(data='{"type":"chunk","content":"half an ans"}'))
        import requests

        raise requests.ConnectionError("connection reset by peer")

    authed.respond_stream = dropping
    ctrl = make_controller(authed)
    ctrl.bootstrap()
    ctrl.send("hello")
    idle(ctrl)
    assert ctrl.conversation.messages[-1].content == "half an ans"
    assert ctrl.busy is False
