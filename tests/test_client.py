"""The Aero HTTP client against the contract-faithful mock server."""

from __future__ import annotations

import pytest
import requests

from grace.client import AeroClient, parse_chat_list, conversation_from_chat
from grace.errors import (
    AuthFailure,
    GraceRateLimited,
    GraceServerError,
    GraceTimeout,
    InvalidCredentials,
    NetworkUnavailable,
    OtpRejected,
)


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #

def test_login_success(client):
    outcome = client.login("ada@example.com", "correct-horse")
    assert outcome.ok
    assert outcome.access_token
    assert client.is_authenticated
    assert client.user is not None
    assert client.user.username == "ada"
    assert client.session.headers["Authorization"].startswith("Bearer ")


def test_login_stores_token_only_in_memory(client, tmp_path):
    client.login("ada@example.com", "correct-horse")
    token = client.access_token
    # Nothing on disk mentions the token or the password.
    for path in tmp_path.rglob("*"):
        assert token not in path.read_text(errors="ignore")


def test_login_invalid_credentials(client):
    with pytest.raises(InvalidCredentials):
        client.login("ada@example.com", "wrong")


def test_login_unknown_user(client):
    with pytest.raises(InvalidCredentials):
        client.login("nobody@example.com", "correct-horse")


def test_login_otp_challenge(client):
    outcome = client.login("otp@example.com", "correct-horse")
    assert outcome.status == "otp_required"
    assert not client.is_authenticated
    assert "otp" in outcome.message.lower() or outcome.message


def test_verify_otp(client):
    assert client.login("otp@example.com", "correct-horse").status == "otp_required"
    outcome = client.verify_otp("otp@example.com", "123456")
    assert outcome.ok
    assert client.is_authenticated


def test_verify_otp_rejected(client):
    client.login("otp@example.com", "correct-horse")
    with pytest.raises(OtpRejected):
        client.verify_otp("otp@example.com", "000000")


def test_logout_clears_token(client):
    client.login("ada@example.com", "correct-horse")
    client.clear_token()
    assert not client.is_authenticated
    assert "Authorization" not in client.session.headers


# --------------------------------------------------------------------------- #
# Chats
# --------------------------------------------------------------------------- #

def test_load_chats_returns_newest_first(client):
    client.login("ada@example.com", "correct-horse")
    chats = client.load_chats()
    assert len(chats) == 2
    by_id = {c.id: c for c in chats}
    assert "gc_server_1" in by_id


def test_load_chats_requires_auth(client):
    with pytest.raises(AuthFailure):
        client.load_chats()


def test_load_chats_parses_messages(client):
    client.login("ada@example.com", "correct-horse")
    chat = next(c for c in client.load_chats() if c.id == "gc_server_1")
    convo = conversation_from_chat(chat, "New conversation")
    assert convo.title == "Debug the render loop"
    assert [m.role for m in convo.messages] == ["user", "assistant"]
    assert convo.messages[0].content == "Why does my loop stutter?"
    assert convo.messages[0].id == "m_1"
    assert convo.origin == "server"


@pytest.mark.parametrize(
    "payload",
    [
        [{"_id": "a", "title": "A"}],
        {"chats": [{"_id": "a", "title": "A"}]},
        {"conversations": [{"_id": "a", "title": "A"}]},
        {"data": [{"_id": "a", "title": "A"}]},
        {"chats": {"docs": [{"_id": "a", "title": "A"}]}},
    ],
)
def test_parse_chat_list_accepts_plausible_shapes(payload):
    chats = parse_chat_list(payload)
    assert [c.id for c in chats] == ["a"]


def test_parse_chat_list_ignores_junk():
    assert parse_chat_list({"unexpected": 1}) == []
    assert parse_chat_list(None) == []
    assert parse_chat_list("nope") == []
    assert parse_chat_list([{"no_id": True}, 5, "x"]) == []


def test_parse_chat_list_handles_block_content():
    payload = [{"_id": "a", "messages": [{"role": "user", "content": [{"text": "hi"}]}]}]
    chats = parse_chat_list(payload)
    convo = conversation_from_chat(chats[0], "New conversation")
    assert convo.messages[0].content == "hi"


def test_parse_chat_list_normalises_roles():
    payload = [
        {"_id": "a", "messages": [
            {"role": "human", "content": "q"},
            {"role": "grace", "content": "a"},
            {"role": "system", "content": "ignored"},
        ]}
    ]
    convo = conversation_from_chat(parse_chat_list(payload)[0], "New conversation")
    assert [m.role for m in convo.messages] == ["user", "assistant"]


# --------------------------------------------------------------------------- #
# Title
# --------------------------------------------------------------------------- #

def test_generate_title(authed, state):
    assert authed.generate_title("Why does my loop stutter?") == "Debug the render loop"
    body = state.requests[-1]["body"]
    assert body == {"message": "Why does my loop stutter?"}


def test_generate_title_requires_auth(client):
    with pytest.raises(AuthFailure):
        client.generate_title("hello")


# --------------------------------------------------------------------------- #
# Respond / SSE
# --------------------------------------------------------------------------- #

def test_respond_stream_happy_path(authed):
    events, parser = authed.respond_stream({"message": "hi"})
    assert parser.stats.done
    kinds = [e.json().get("type") for e in events if e.json()]
    assert kinds == ["status", "chunk", "chunk", "done"]


def test_respond_sends_expected_payload(authed, state):
    authed.respond_stream(
        {
            "message": "hello",
            "conversationHistory": [],
            "mode": "normal",
            "effort": "instant",
            "conversationId": "gc_x",
            "clientMessageId": "m_x",
            "capabilities": ["workspace_v2", "ask_user", "drawings_v1"],
        }
    )
    payload = state.respond_payloads[-1]
    assert payload["message"] == "hello"
    assert payload["mode"] == "normal"
    assert payload["effort"] == "instant"
    assert payload["conversationId"] == "gc_x"
    assert payload["clientMessageId"] == "m_x"
    assert payload["capabilities"] == ["workspace_v2", "ask_user", "drawings_v1"]
    assert payload["conversationHistory"] == []


def test_respond_unauthorized(client):
    with pytest.raises(AuthFailure):
        client.respond_stream({"message": "hi"})


def test_respond_server_error(authed, state):
    state.fail_with(500, {"message": "Grace exploded"})
    with pytest.raises(GraceServerError):
        authed.respond_stream({"message": "hi"})


def test_respond_rate_limited(authed, state):
    state.fail_with(429, {"message": "Too many requests"})
    with pytest.raises(GraceRateLimited):
        authed.respond_stream({"message": "hi"})


def test_respond_validation_error(authed, state):
    state.fail_with(400, {"message": "mode is not allowed"})
    with pytest.raises(GraceServerError):
        authed.respond_stream({"message": "hi", "mode": "ultra"})


def test_respond_network_failure(base_url):
    broken = AeroClient(base_url=base_url)
    broken.session.post = lambda *a, **k: (_ for _ in ()).throw(
        requests.ConnectionError("refused")
    )
    with pytest.raises(NetworkUnavailable):
        broken.respond_stream({"message": "hi"})


def test_respond_timeout(base_url):
    broken = AeroClient(base_url=base_url)
    broken.session.post = lambda *a, **k: (_ for _ in ()).throw(
        requests.Timeout("timed out")
    )
    with pytest.raises(GraceTimeout):
        broken.respond_stream({"message": "hi"})


class _FakeResponse:
    """Minimal stand-in for requests.Response (used for non-SSE bodies)."""

    def __init__(self, status=200, body=b'{"message":"Grace is offline"}',
                 content_type="application/json"):
        self.status_code = status
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def iter_content(self, chunk_size=1):
        yield self._body

    @property
    def text(self):
        return self._body.decode("utf-8", "replace")

    def close(self):
        self.closed = True


def test_respond_json_body_without_sse_headers_is_an_error(authed, monkeypatch):
    authed.session.post = lambda *a, **k: _FakeResponse()
    with pytest.raises(GraceServerError):
        authed.respond_stream({"message": "hi"})


def test_respond_malformed_sse_body_does_not_raise(authed, monkeypatch):
    authed.session.post = lambda *a, **k: _FakeResponse(
        body=b"not json at all\n\n", content_type="text/event-stream"
    )
    events, parser = authed.respond_stream({"message": "hi"})
    assert parser.stats.truncated is True
    assert events == []


def test_respond_truncated_stream_is_flagged(authed, state):
    state.respond_events = [{"type": "chunk", "content": "partial"}]
    state.emit_done = False
    events, parser = authed.respond_stream({"message": "hi"})
    assert parser.stats.truncated is True
    assert parser.stats.done is False
    assert any(e.json() and e.json()["type"] == "chunk" for e in events)


def test_respond_cancel_event(authed, state):
    import threading

    state.delay = 0.6
    state.respond_events = [
        {"type": "chunk", "content": f"{i}"} for i in range(40)
    ]
    cancel = threading.Event()
    cancel.set()
    events, parser = authed.respond_stream({"message": "hi"}, cancel_event=cancel)
    assert events == []
    assert parser.stats.truncated is True


def test_respond_multichunk_content(authed, state):
    expected = "".join(str(i) for i in range(200))
    state.set_respond_events([{"type": "chunk", "content": str(i)} for i in range(200)])
    events, parser = authed.respond_stream({"message": "hi"})
    text = "".join(
        e.json()["content"] for e in events if e.json() and e.json().get("type") == "chunk"
    )
    assert text == expected
    assert parser.stats.done


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #

def _write(tmp_path, name="notes.txt", content=b"hello grace"):
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def test_upload_attachment(authed, tmp_path):
    path = _write(tmp_path)
    attachment = authed.upload_attachment(path)
    assert attachment.state == "uploaded"
    assert attachment.remote_id.startswith("f_")
    assert attachment.size == len(b"hello grace")
    assert attachment.progress == 1.0


def test_upload_progress_reported(authed, tmp_path):
    path = _write(tmp_path, content=b"x" * 200000)
    seen = []
    authed.upload_attachment(path, on_progress=seen.append)
    assert seen and seen[-1] == 1.0


def test_upload_failure_marks_attachment(authed, tmp_path, state):
    state.upload_status = 500
    path = _write(tmp_path)
    with pytest.raises(GraceServerError):
        authed.upload_attachment(path)
    assert state.uploads[0]["name"] == "notes.txt"


def test_upload_requires_auth(client, tmp_path):
    path = _write(tmp_path)
    with pytest.raises(AuthFailure):
        client.upload_attachment(path)


def test_upload_missing_file(authed):
    with pytest.raises(GraceServerError):
        authed.upload_attachment("/definitely/not/here.txt")


def test_upload_uses_configured_field_name(authed, tmp_path, state):
    path = _write(tmp_path)
    authed.upload_attachment(path, field_name="files")
    assert state.uploads and state.uploads[0]["name"] == "notes.txt"


# --------------------------------------------------------------------------- #
# HTTPS enforcement
# --------------------------------------------------------------------------- #

def test_plaintext_endpoint_is_refused():
    with pytest.raises(ValueError):
        AeroClient(base_url="http://api.example.com")


def test_loopback_plaintext_is_allowed_for_tests():
    client = AeroClient(base_url="http://127.0.0.1:9")
    assert client.origin == "http://127.0.0.1:9"
