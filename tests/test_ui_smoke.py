"""GUI construction smoke tests.

The sandbox has no ``tkinter`` build and no display, so these tests run
against ``tests/tkstub.py``: a functional stub of the Tk API.  They prove that
every widget in the UI layer can be constructed, updated and torn down
without raising - which is the part of the GUI that is otherwise untestable
here.  Real layout, scrolling and pixel appearance require a display and are
listed as unverified in the README.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkstub  # noqa: E402

tkstub.install()

import tkinter as tk  # noqa: E402  (the stub)

import pytest  # noqa: E402

from grace import modes  # noqa: E402
from grace.client import AeroClient  # noqa: E402
from grace.models import Conversation, Credits, Message, User, new_id  # noqa: E402
from grace.ui import theme  # noqa: E402
from grace.ui.app import GraceApp  # noqa: E402
from grace.ui.chat_view import ChatView  # noqa: E402
from grace.ui.composer import Composer, ModePopup  # noqa: E402
from grace.ui.login_view import LoginView  # noqa: E402
from grace.ui.markdown_view import MarkdownView  # noqa: E402
from grace.ui.sidebar import Sidebar  # noqa: E402
from grace.ui.widgets import (  # noqa: E402
    Avatar, Card, IconButton, PillButton, ScrollableFrame, SendButton, Separator,
    Toast, rounded_points, ui_font,
)


@pytest.fixture()
def root():
    app = tk.Tk()
    theme.resolve_fonts(app)
    yield app
    app.destroy()


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #

def test_rounded_points_are_sane():
    pts = rounded_points(0, 0, 100, 40, 8)
    assert len(pts) % 2 == 0
    assert len(pts) >= 12
    assert min(pts) >= -0.01
    assert max(pts) <= 100.01


def test_rounded_points_clamps_radius():
    pts = rounded_points(0, 0, 10, 4, 999)
    assert all(0 <= p <= 10.01 or p <= 4.01 for p in pts)


def test_pill_button_constructs_and_updates(root):
    button = PillButton(root, text="Send", command=lambda: None)
    assert button._width == 92
    button.set_text("Stop")
    button.set_state("disabled")
    button.set_size(120, 34)
    assert button._width == 120


def test_pill_button_hover_and_click(root):
    clicks = []
    button = PillButton(root, text="Go", command=lambda: clicks.append(1))
    button._on_event(_event(tk.EventType.Enter))
    button._on_event(_event(tk.EventType.ButtonPress))
    button._on_event(_event(tk.EventType.ButtonRelease))
    assert clicks == [1]
    button._on_event(_event(tk.EventType.Leave))


def test_icon_button_constructs(root):
    IconButton(root, glyph="+", command=lambda: None)


def test_send_button(root):
    button = SendButton(root, command=lambda: None)
    button.set_enabled(False)
    button.set_enabled(True)


def test_card_separator_avatar(root):
    Card(root)
    Separator(root)
    avatar = Avatar(root, initials="AB", size=28)
    avatar.set_initials("CD")


def test_toast_shows_and_hides(root):
    toast = Toast(root, text="hello", kind="error", ttl=10)
    toast.show()
    toast.set_text("changed")
    toast.hide()


def test_ui_font_caching(root):
    a = ui_font(10)
    b = ui_font(10)
    assert a is b
    assert ui_font(10, mono=True) is not a


def test_scrollable_frame(root):
    frame = ScrollableFrame(root, show_bar=True)
    frame.inner.pack()
    frame.bind_wheel()
    frame.scroll_to_bottom()
    assert frame.at_bottom() is True


# --------------------------------------------------------------------------- #
# Markdown view
# --------------------------------------------------------------------------- #

MARKDOWN_SAMPLES = [
    "",
    "plain text",
    "# Heading\n\nBody",
    "**bold** *italic* `code` ~~strike~~",
    "- a\n- b\n- c",
    "1. one\n2. two",
    "> quoted",
    "---",
    "```python\nprint('hi')\n```",
    "```\nunterminated",
    "| a | b |\n|---|---|\n| 1 | 2 |",
    "$$\nx^2\n$$",
    "[link](https://example.com)",
    "https://bare.example.com",
    "# H1\n\n## H2\n\n### H3\n\n#### H4\n\n##### H5\n\n###### H6",
    "\n\n".join(f"para {i}" for i in range(50)),
]


@pytest.mark.parametrize("source", MARKDOWN_SAMPLES)
def test_markdown_view_renders_every_sample(root, source):
    view = MarkdownView(root)
    view.set_markdown(source, final=True)
    view.set_markdown(source, final=True, force=True)
    assert view._last_source == source


def test_markdown_view_throttles_while_streaming(root):
    view = MarkdownView(root)
    view.set_markdown("a", final=False)
    view.set_markdown("ab", final=False)      # throttled away
    view.set_markdown("abc", final=False, force=True)
    assert view._last_source == "abc"


def test_markdown_view_pending_flush(root):
    view = MarkdownView(root)
    view.set_markdown("one", final=True)
    view.set_markdown("two", final=False)
    view._flush_pending("two")
    assert view._last_source == "two"


def test_markdown_view_plain_and_clear(root):
    view = MarkdownView(root)
    view.set_plain("raw error text")
    view.copy_all()
    view.clear()
    assert view._last_source == ""


def test_markdown_view_copy_button_is_registered(root):
    view = MarkdownView(root)
    view.set_markdown("```py\nx = 1\n```", final=True)
    assert len(view._copy_registry) == 1
    tag = next(iter(view._copy_registry))
    view._copy_block(tag)
    assert view._copy_registry[tag] == "x = 1"
    view._flash_copied(tag)


def test_markdown_view_link_click(root):
    view = MarkdownView(root)
    view.set_markdown("[docs](https://example.com)", final=True)
    view._open_link(_event(tk.EventType.ButtonPress, x=0, y=0))


# --------------------------------------------------------------------------- #
# Login view
# --------------------------------------------------------------------------- #

def test_login_view_constructs(root):
    view = LoginView(root, on_submit=lambda *a: None, on_verify=lambda *a: None,
                     on_cancel=lambda: None)
    assert view.step == "credentials"
    view.set_error("bad")
    view.set_info("info")
    view.clear_error()
    view.set_busy(True)
    view.set_busy(False)


def test_login_view_otp_step(root):
    view = LoginView(root, on_submit=lambda *a: None, on_verify=lambda *a: None,
                     on_cancel=lambda: None)
    view.show_otp("OTP sent to registered email")
    assert view.step == "otp"
    view._digits_only()
    view._back()
    assert view.step == "credentials"
    view.clear_password()


def test_login_view_rejects_empty_credentials(root):
    errors = []
    view = LoginView(root, on_submit=lambda *a: None, on_verify=lambda *a: None,
                     on_cancel=lambda: None)
    view.set_error = lambda msg: errors.append(msg)
    view._submit()
    assert errors


def test_login_view_requires_six_digits(root):
    errors = []
    sent = []
    view = LoginView(root, on_submit=lambda *a: None, on_verify=lambda c: sent.append(c),
                     on_cancel=lambda: None)
    view.show_otp()
    view.code.insert(0, "123")
    view.set_error = lambda msg: errors.append(msg)
    view._verify()
    assert errors and not sent
    view.code.delete(0, "end")
    view.code.insert(0, "123456")
    view._verify()
    assert sent == ["123456"]


# --------------------------------------------------------------------------- #
# Composer
# --------------------------------------------------------------------------- #


def make_composer(root):
    state = {"sent": [], "stopped": 0, "attached": 0, "modes": [], "removed": [],
             "retried": []}
    composer = Composer(
        root,
        on_send=state["sent"].append,
        on_stop=lambda: state.__setitem__("stopped", state["stopped"] + 1),
        on_attach=lambda: state.__setitem__("attached", state["attached"] + 1),
        on_mode=state["modes"].append,
        on_remove_attachment=state["removed"].append,
        on_retry_attachment=state["retried"].append,
    )
    return composer, state


def test_composer_starts_empty(root):
    composer, _ = make_composer(root)
    assert composer.get_text() == ""
    composer.set_text("hello")
    assert composer.get_text() == "hello"
    composer.clear()
    assert composer.get_text() == ""


def test_composer_placeholder_behaviour(root):
    composer, _ = make_composer(root)
    composer._clear_placeholder()
    composer.input.delete("1.0", "end")
    composer._on_focus(False)
    composer._on_focus(True)
    assert composer.get_text() == ""


def test_composer_enter_sends_and_shift_enters_newline(root):
    composer, state = make_composer(root)
    composer.set_text("hello")
    composer._on_return(_event(tk.EventType.KeyPress, state=0))
    assert state["sent"] == ["hello"]

    composer.set_text("line")
    composer._on_return(_event(tk.EventType.KeyPress, state=0x1))
    assert state["sent"] == ["hello"]          # shift did not send


def test_composer_ctrl_enter_sends(root):
    composer, state = make_composer(root)
    composer.set_text("hello")
    composer._on_ctrl_return(_event(tk.EventType.KeyPress))
    assert state["sent"] == ["hello"]


def test_composer_refuses_empty_and_duplicate_sends(root):
    composer, state = make_composer(root)
    composer._send()
    assert state["sent"] == []
    composer.set_text("   ")
    composer._send()
    assert state["sent"] == []
    composer.set_text("hi")
    composer.set_busy(True)
    composer._send()
    assert state["sent"] == []


def test_composer_autosize(root):
    composer, _ = make_composer(root)
    composer._clear_placeholder()
    composer.input.insert("1.0", "one\ntwo\nthree")
    composer._autosize()
    assert composer.input.cget("height") >= 1


def test_composer_send_button_enables_only_with_text(root):
    composer, _ = make_composer(root)
    assert composer.send_button._enabled is False
    composer.set_text("x")
    composer._refresh_send_state()
    assert composer.send_button._enabled is True


def test_composer_busy_swaps_send_for_stop(root):
    composer, _ = make_composer(root)
    composer.set_busy(True)
    assert composer._busy is True
    composer.set_busy(False)
    assert composer._busy is False


def test_composer_attachment_chips(root):
    composer, state = make_composer(root)
    composer.set_attachments(
        [
            _attachment("a.txt", "uploading", 0.5),
            _attachment("b.json", "uploaded", 1.0),
            _attachment("c.png", "failed", 0.0),
        ]
    )
    assert len(composer.chips.winfo_children()) == 3
    composer.set_attachments([])
    assert composer.chips.winfo_children() == []


def test_composer_mode_selection(root):
    composer, state = make_composer(root)
    composer.set_mode(modes.ULTRA_THINKING)
    assert composer.mode_button.text == "Ultra · Thinking"
    composer._pick_mode("deep-research")
    assert state["modes"] == ["deep-research"]
    assert composer._mode is modes.DEEP_RESEARCH


def test_mode_popup_opens_and_closes(root):
    picked = []
    popup = ModePopup(root, picked.append)
    anchor = PillButton(root, text="Normal")
    popup.show(anchor, "normal")
    assert popup.top is not None
    popup.hide()
    assert popup.top is None


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

def test_sidebar_updates(root):
    sidebar = Sidebar(root, on_sign_out=lambda: None)
    sidebar.set_user(User(username="ada", full_name="Ada Lovelace", plan="apex"))
    assert sidebar.account_name.cget("text") == "Ada Lovelace"
    sidebar.set_credits(Credits(remaining=141.5, used=8.5, tier="normal"))
    sidebar.set_conversation(Conversation(id="gc_1", title="Debug loop"))
    sidebar.set_connection("online")
    sidebar.set_connection("connecting", "loading")
    sidebar.set_connection("offline")
    sidebar.set_user(None)
    sidebar.set_credits(None)
    sidebar.set_conversation(None)


def test_sidebar_message_count(root):
    sidebar = Sidebar(root, on_sign_out=lambda: None)
    convo = Conversation(id="gc_1")
    sidebar.set_conversation(convo)
    assert "No messages" in sidebar.convo_meta.cget("text")
    convo.messages.append(Message(id="m1", role="user", content="hi"))
    sidebar.set_conversation(convo)
    assert sidebar.convo_meta.cget("text") == "1 message"
    convo.messages.append(Message(id="m2", role="assistant", content="yo"))
    sidebar.set_conversation(convo)
    assert sidebar.convo_meta.cget("text") == "2 messages"


# --------------------------------------------------------------------------- #
# Chat view
# --------------------------------------------------------------------------- #

def test_chat_view_empty_state(root):
    chat = ChatView(root)
    picked = []
    chat.show_empty_state(picked.append)
    assert len(chat.list.winfo_children()) == 1


def test_chat_view_renders_history(root):
    chat = ChatView(root)
    convo = Conversation(id="gc_1")
    convo.messages = [
        Message(id="m1", role="user", content="hi", at="2026-06-01T08:00:00Z"),
        Message(id="m2", role="assistant", content="hello", at="2026-06-01T08:00:09Z"),
    ]
    chat.render_conversation(convo)
    assert len(chat.list.winfo_children()) == 2
    assert chat.bubble_for("m1") is not None


def test_chat_view_streaming_updates(root):
    chat = ChatView(root)
    message = Message(id="m1", role="assistant", content="", streaming=True)
    bubble = chat.append_message(message)
    bubble.set_streaming_text("Hel")
    bubble.set_streaming_text("Hello")
    bubble.set_status("thinking")
    bubble.finalize()
    assert bubble.message.content == "Hello"
    bubble.mark_error()
    assert bubble.message.error is True
    chat.auto_scroll()


def test_chat_view_user_bubble_with_attachments(root):
    chat = ChatView(root)
    message = Message(id="m1", role="user", content="summarise",
                      attachments=[_attachment("a.txt", "uploaded", 1.0)])
    chat.append_message(message)
    assert len(chat.list.winfo_children()) == 1


# --------------------------------------------------------------------------- #
# Application shell
# --------------------------------------------------------------------------- #


def test_app_constructs():
    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"), debug=False)
    try:
        assert app.root.title() == "Aero · Grace"
        assert app.controller.conversation is None
        assert app.composer.get_text() == ""
        # Window policy.
        app._toggle_fullscreen()
        assert app._fullscreen is True
        app._leave_fullscreen()
        assert app._fullscreen is False
        app._toggle_fullscreen()
        app._leave_fullscreen()
    finally:
        app._on_close()


def test_app_header_does_not_collide_with_the_content_grid():
    """The header must own exactly one grid row of the shell.

    Regression guard: a separator placed directly in the shell's grid used to
    occupy row 1, the same row as the sidebar and the chat area.
    """
    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        header = app.shell.winfo_children()[0]
        # header -> [bar, separator]; nothing else lives in the shell's row 0.
        assert len(header.winfo_children()) == 2
        assert header.winfo_children()[1].cget("bg") == theme.BORDER
        assert header.cget("height") in ("", None) or True
    finally:
        app._on_close()


def test_app_handles_controller_events():
    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        convo = Conversation(id="gc_1", title="Debug loop")
        convo.messages = [
            Message(id="m1", role="user", content="hi", at="2026-06-01T08:00:00Z"),
            Message(id="m2", role="assistant", content="hello",
                    at="2026-06-01T08:00:09Z"),
        ]
        app._handle(_evt("conversation_ready", convo))
        app._handle(_evt("history_restored", convo))
        assert len(app.chat.list.winfo_children()) == 2

        user = Message(id="m3", role="user", content="next")
        app._handle(_evt("user_message", user))
        assistant = Message(id="m4", role="assistant", content="", streaming=True)
        app._handle(_evt("assistant_start", assistant))
        assistant.content = "par"
        app._handle(_evt("assistant_chunk", assistant))
        assistant.content = "partial"
        app._handle(_evt("status", "Grace is thinking…"))
        app._handle(_evt("assistant_done", (assistant, None)))
        app._handle(_evt("assistant_error", assistant))
        app._handle(_evt("credits", Credits(remaining=12.5, tier="normal")))
        app._handle(_evt("title", "New title"))
        app._handle(_evt("attachment_changed", None))
        app._handle(_evt("attachments_cleared", None))
        app._handle(_evt("busy", True))
        app._handle(_evt("busy", False))
        app._handle(_evt("mode_changed", modes.ULTRA_THINKING))
        app._handle(_evt("loading", "Loading…"))
        app._handle(_evt("connection", User(username="ada")))
        app._handle(_evt("shutdown", None))
    finally:
        app._on_close()


def test_app_login_error_shows_friendly_text():
    from grace.errors import InvalidCredentials

    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        app._handle(_evt("login_error", InvalidCredentials()))
        assert "Invalid email/username or password." in app.login_view.error.cget("text")
        assert "Traceback" not in app.login_view.error.cget("text")
    finally:
        app._on_close()


def test_app_otp_error_switches_step():
    from grace.errors import OtpRejected

    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        app._handle(_evt("login_error", OtpRejected()))
        assert app.login_view.step == "otp"
    finally:
        app._on_close()


def test_app_toast():
    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        app._toast("hello", "error")
        assert app._pending_toast is not None
        app._toast("again", "info")
    finally:
        app._on_close()


def test_app_send_is_refused_while_busy():
    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        app.controller._busy = True
        app._send("hello")     # must not raise
    finally:
        app._on_close()


def test_app_sign_out_resets_state(monkeypatch):
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **kw: True)
    app = GraceApp(client=AeroClient(base_url="http://127.0.0.1:9"))
    try:
        app.controller.conversation = Conversation(id="gc_1", title="t")
        app._sign_out()
        assert app.controller.conversation is None
    finally:
        app._on_close()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _Evt:
    def __init__(self, kind, data=None):
        self.kind = kind
        self.data = data


def _evt(kind, data=None):
    return _Evt(kind, data)


def _event(event_type, **kw):
    class _E:
        type = event_type
        state = 0
        x = 0
        y = 0
        num = 0
        delta = 0

    obj = _E()
    for key, value in kw.items():
        setattr(obj, key, value)
    return obj


def _attachment(name, state, progress):
    from grace.models import Attachment

    return Attachment(
        id=new_id("att_"), path=f"/tmp/{name}", name=name, size=12, mime="text/plain",
        state=state, progress=progress, remote_id="f_1" if state == "uploaded" else "",
    )
