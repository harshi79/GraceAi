"""A contract-faithful local stand-in for the Aero REST API.

Only the endpoints the client actually speaks are implemented, and each one
mirrors the shape that was observed on the real API:

* ``POST /api/auth/login``      ``{identifier, password}`` -> ``{accessToken, ...user}``
* ``POST /api/auth/login/verify-otp`` ``{identifier, code}`` -> ``{accessToken}``
* ``GET  /api/ai/grace/chats``  -> list of conversations
* ``POST /api/ai/grace/generate-title`` ``{message}`` -> ``{title}``
* ``POST /api/ai/grace/respond`` -> SSE: ``status`` / ``chunk`` / ``done`` / ``[DONE]``
* ``POST /api/ai/grace/upload`` -> multipart -> ``{fileId, name, sizeBytes}``

Everything is in-process (a threaded HTTP server on 127.0.0.1), so the test
suite never touches the network.
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Fixture data
# --------------------------------------------------------------------------- #

USERS: Dict[str, Dict[str, Any]] = {
    "ada@example.com": {
        "_id": "u_ada",
        "username": "ada",
        "fullName": "Ada Lovelace",
        "email": "ada@example.com",
        "profilePic": "",
        "plan": "apex",
        "loginOtpEnabled": False,
        "joinedAt": "2024-01-04T10:00:00Z",
    },
    "grace@example.com": {
        "_id": "u_grace",
        "username": "gracehopper",
        "fullName": "Grace Hopper",
        "email": "grace@example.com",
        "loginOtpEnabled": True,
        "joinedAt": "2023-11-12T09:30:00Z",
    },
}

OTP_USER = "otp@example.com"

CHATS: List[Dict[str, Any]] = [
    {
        "_id": "gc_server_1",
        "title": "Debug the render loop",
        "createdAt": "2026-06-01T08:00:00Z",
        "updatedAt": "2026-06-02T11:22:00Z",
        "messages": [
            {"_id": "m_1", "role": "user", "content": "Why does my loop stutter?",
             "createdAt": "2026-06-01T08:00:00Z"},
            {"_id": "m_2", "role": "assistant",
             "content": "You are allocating inside the loop.",
             "createdAt": "2026-06-01T08:00:09Z",
             "meta": {"tier": "normal", "effort": "instant", "thinking": False}},
        ],
    },
    {
        "_id": "gc_server_2",
        "title": "Plan the launch",
        "createdAt": "2026-05-02T08:00:00Z",
        "updatedAt": "2026-05-03T09:00:00Z",
        "messages": [
            {"_id": "m_3", "role": "user", "content": "Draft a launch plan.",
             "createdAt": "2026-05-02T08:00:00Z"},
        ],
    },
]

TOKENS = {"ada@example.com": "tok_ada_0123456789", OTP_USER: "tok_otp_0123456789"}


class MockAero:
    """Mutable scenario state shared between the handler and the tests."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.chats = json.loads(json.dumps(CHATS))
        self.tokens = dict(TOKENS)
        #: SSE events emitted by the next ``/respond`` call.
        self.respond_events: List[Dict[str, Any]] = [
            {"type": "status", "content": "Grace is thinking…"},
            {"type": "chunk", "content": "Hello"},
            {"type": "chunk", "content": " there."},
            {
                "type": "done",
                "content": "",
                "fullContent": "Hello there.",
                "usedCredits": 1.25,
                "remainingCredits": 141.5,
                "tier": "normal",
                "thinking": False,
                "effort": "instant",
                "updatedAt": "2026-06-02T11:22:00Z",
            },
        ]
        self.status = 200
        self.error_body: Dict[str, Any] = {}
        self.upload_status = 200
        self.require_auth = True
        self.emit_done = True
        self.delay = 0.0
        self.title = "Debug the render loop"
        #: Recorded requests (URL -> parsed body / headers of interest).
        self.requests: List[Dict[str, Any]] = []
        self.respond_payloads: List[Dict[str, Any]] = []
        self.uploads: List[Dict[str, Any]] = []

    # -- scenario helpers ---------------------------------------------- #
    def set_respond_events(self, events: List[Dict[str, Any]]) -> None:
        self.respond_events = events

    def fail_with(self, status: int, body: Dict[str, Any]) -> None:
        self.status = status
        self.error_body = body


STATE = MockAero()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state = STATE

    # -- plumbing ------------------------------------------------------ #
    def log_message(self, *_args) -> None:  # silence the test output
        return

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not self.state.require_auth:
            return True
        header = self.headers.get("Authorization", "")
        return header.startswith("Bearer ") and header[7:] in self.state.tokens.values()

    def _unauthorized(self) -> None:
        self._send_json(401, {"message": "Unauthorized - No token provided",
                              "code": "NO_TOKEN"})

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return {}

    def _record(self, body: Any) -> None:
        self.state.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization", ""),
                "content_type": self.headers.get("Content-Type", ""),
                "body": body,
            }
        )

    # -- routes -------------------------------------------------------- #
    def do_POST(self) -> None:  # noqa: N802
        if self.state.delay:
            time.sleep(self.state.delay)
        path = self.path.split("?")[0]

        if path == "/api/auth/login":
            body = self._read_json()
            self._record(body)
            identifier = str(body.get("identifier") or "")
            password = str(body.get("password") or "")
            if identifier == OTP_USER and password == "correct-horse":
                self._send_json(200, {"message": "OTP sent to registered email"})
                return
            user = USERS.get(identifier)
            if user is None or password != "correct-horse":
                self._send_json(401, {"message": "Invalid credentials"})
                return
            self._send_json(200, {"accessToken": self.state.tokens[identifier], **user})
            return

        if path == "/api/auth/login/verify-otp":
            body = self._read_json()
            self._record(body)
            if str(body.get("code")) != "123456":
                self._send_json(401, {"message": "Invalid or expired code"})
                return
            self._send_json(200, {"accessToken": self.state.tokens[OTP_USER],
                                  **USERS.get(OTP_USER, {})})
            return

        if path == "/api/ai/grace/respond":
            body = self._read_json()
            self.state.respond_payloads.append(body)
            self._record(body)
            if not self._authorized():
                self._unauthorized()
                return
            if self.state.status >= 400:
                self._send_json(self.state.status, self.state.error_body)
                return
            self._stream()
            return

        if path == "/api/ai/grace/generate-title":
            body = self._read_json()
            self._record(body)
            if not self._authorized():
                self._unauthorized()
                return
            self._send_json(200, {"title": self.state.title})
            return

        if path == "/api/ai/grace/upload":
            if not self._authorized():
                self._unauthorized()
                return
            self._upload()
            return

        self._send_json(404, {"message": f"Cannot POST {self.path}"})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/ai/grace/chats":
            self._record(None)
            if not self._authorized():
                self._unauthorized()
                return
            self._send_json(200, self.state.chats)
            return
        self._send_json(404, {"message": f"Cannot GET {self.path}"})

    # -- SSE ----------------------------------------------------------- #
    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in self.state.respond_events:
            self.wfile.write(b"data: " + json.dumps(event).encode("utf-8") + b"\n\n")
            self.wfile.flush()
        if self.state.emit_done:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        self.close_connection = True

    # -- multipart ----------------------------------------------------- #
    def _upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(400, {"message": "Expected multipart/form-data"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
        parts = raw.split(("--" + boundary).encode("utf-8"))
        files = []
        for part in parts:
            if not part.strip() or part.strip() == b"--":
                continue
            head, _, payload = part.partition(b"\r\n\r\n")
            payload = payload.rstrip(b"\r\n")
            headers = head.decode("utf-8", "replace")
            match = re.search(r'filename="([^"]*)"', headers)
            if not match:
                continue
            name = match.group(1)
            files.append({"name": name, "size": len(payload), "data": payload})
        self.state.uploads.extend(files)
        if self.state.upload_status >= 400:
            self._send_json(self.state.upload_status, {"message": "Upload rejected"})
            return
        self._send_json(
            200,
            {"fileId": f"f_{files[0]['name'] if files else 'none'}",
             "name": files[0]["name"] if files else "",
             "sizeBytes": files[0]["size"] if files else 0},
        )


def start_server(state: Optional[MockAero] = None):
    """Start the mock server and return ``(server, thread, state)``."""
    handler_state = state or STATE
    handler = type("BoundHandler", (Handler,), {"state": handler_state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, handler_state


def stop_server(server) -> None:
    server.shutdown()
    server.server_close()
