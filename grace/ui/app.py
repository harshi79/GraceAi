"""The application shell: window chrome, header, and controller wiring.

Threading model
---------------
The controller emits events from its worker thread.  Every event is pushed
onto a :class:`queue.Queue` and drained on the Tk main loop by a single
``after`` poller, so no widget is ever touched from a background thread and
streaming can never race with a user action.
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from typing import Optional
from tkinter import filedialog, messagebox

from .. import config, modes
from ..client import AeroClient
from ..controller import (
    ASSISTANT_CHUNK,
    ASSISTANT_DONE,
    ASSISTANT_ERROR,
    ASSISTANT_START,
    ATTACHMENTS_CLEARED,
    ATTACHMENT_CHANGED,
    BUSY,
    CONNECTION,
    CONVERSATION_READY,
    CREDITS,
    ERROR,
    Event,
    GraceController,
    HISTORY_RESTORED,
    LOADING,
    MODE_CHANGED,
    NEW_CONVERSATION_TITLE,
    STATUS,
    TITLE,
    USER_MESSAGE,
)
from ..errors import AeroError
from ..logutil import enable_debug, log
from ..models import Conversation, Message
from . import theme
from .chat_view import ChatView
from .composer import Composer
from .login_view import LoginView
from .sidebar import Sidebar
from .widgets import PillButton, Toast, ui_font

POLL_MS = 30


class GraceApp:
    """Owns the Tk root and mediates between the controller and the views."""

    def __init__(self, client: Optional[AeroClient] = None, debug: bool = False) -> None:
        if debug:
            enable_debug()
        self.client = client or AeroClient()
        self.controller = GraceController(self.client, on_event=self._on_controller_event)
        self.events: "queue.Queue[Event]" = queue.Queue()
        self._identifier = ""
        self._fullscreen = False
        self._stream_message: Optional[Message] = None
        self._pending_toast: Optional[Toast] = None

        self.root = tk.Tk()
        theme.resolve_fonts(self.root)
        self._configure_window()
        self._build_chrome()
        self._build_login()
        self._bind_keys()

        self.root.after(POLL_MS, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # Window
    # ------------------------------------------------------------------ #
    def _configure_window(self) -> None:
        win = config.DEFAULT_WINDOW
        self.root.title(win.title)
        self.root.configure(bg=theme.BG)
        self.root.minsize(win.min_width, win.min_height)
        self.root.geometry(f"{win.default_width}x{win.default_height}")
        self._maximise()

    def _maximise(self) -> None:
        try:
            self.root.attributes("-zoomed", True)
            return
        except Exception:
            pass
        try:
            self.root.state("zoomed")
            return
        except Exception:
            pass
        try:
            self.root.wm_state("zoomed")
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ #
    # Chrome
    # ------------------------------------------------------------------ #
    def _build_chrome(self) -> None:
        self.shell = tk.Frame(self.root, bg=theme.BG)
        self.shell.pack(fill="both", expand=True)
        self.shell.rowconfigure(1, weight=1)
        self.shell.columnconfigure(1, weight=1)

        self._build_header()

        self.sidebar = Sidebar(self.shell, on_sign_out=self._sign_out, background=theme.SURFACE)
        self.sidebar.grid(row=1, column=0, sticky="nsew")

        main = tk.Frame(self.shell, bg=theme.BG)
        main.grid(row=1, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        self.toast_host = tk.Frame(main, bg=theme.BG)
        self.toast_host.grid(row=0, column=0, sticky="ew")

        self.chat = ChatView(main, background=theme.BG)
        self.chat.grid(row=1, column=0, sticky="nsew")

        self.composer = Composer(
            main,
            on_send=self._send,
            on_stop=self._stop,
            on_attach=self._attach,
            on_mode=self._set_mode,
            on_remove_attachment=self._remove_attachment,
            on_retry_attachment=self._retry_attachment,
            background=theme.BG,
        )
        self.composer.grid(row=2, column=0, sticky="ew")

        self.chat.show_empty_state(self._use_suggestion)

    def _build_header(self) -> None:
        header = tk.Frame(self.shell, bg=theme.BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=0)
        header.rowconfigure(0, weight=1)

        bar = tk.Frame(header, bg=theme.BG, height=52)
        bar.grid(row=0, column=0, columnspan=5, sticky="ew")
        bar.grid_propagate(False)
        bar.columnconfigure(1, weight=1)

        tk.Label(
            bar, text="Grace", bg=theme.BG, fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD, bold=True),
        ).grid(row=0, column=0, padx=(20, 12), sticky="w")

        self.header_title = tk.Label(
            bar, text=NEW_CONVERSATION_TITLE, bg=theme.BG, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_SM), anchor="w",
        )
        self.header_title.grid(row=0, column=1, sticky="w")

        self.header_credits = tk.Label(
            bar, text="", bg=theme.BG, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS),
        )
        self.header_credits.grid(row=0, column=2, sticky="e", padx=(12, 8))

        self.header_mode = tk.Label(
            bar, text=modes.default().short_label, bg=theme.BG,
            fg=theme.TEXT_FAINT, font=ui_font(theme.SIZE_XS),
        )
        self.header_mode.grid(row=0, column=3, sticky="e", padx=(0, 8))

        PillButton(
            bar, text="Fullscreen", command=self._toggle_fullscreen, variant="subtle",
            width=104, height=26, font_size=theme.SIZE_XS, background=theme.BG,
        ).grid(row=0, column=4, sticky="e", padx=(0, 16))

        tk.Frame(header, bg=theme.BORDER, height=1).grid(
            row=1, column=0, columnspan=5, sticky="ew"
        )

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    def _build_login(self) -> None:
        self.login_view = LoginView(
            self.root,
            on_submit=self._login,
            on_verify=self._verify_otp,
            on_cancel=self._cancel_otp,
            background=theme.BG,
        )
        self.login_view.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Keys
    # ------------------------------------------------------------------ #
    def _bind_keys(self) -> None:
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self._leave_fullscreen())
        self.root.bind("<Control-l>", lambda e: self._focus_composer())
        self.root.bind("<Control-Shift-D>", lambda e: self._toggle_debug())
        self.root.bind("<Control-d>", lambda e: self._toggle_debug())
        self.root.bind("<Configure>", self._on_configure)

    def _focus_composer(self) -> None:
        self.composer.focus_input()

    def _toggle_debug(self) -> None:
        from ..logutil import log as app_log

        if app_log.level == 10:
            app_log.setLevel(20)
            self._toast("Debug logging off", "info")
        else:
            app_log.setLevel(10)
            self._toast("Debug logging on (credentials are still redacted)", "info")

    def _on_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        # The composer and sidebar are laid out by the grid manager, so a
        # resize only needs the message list to re-wrap and re-evaluate its
        # scroll region.
        self.root.after_idle(self.chat.scroll._on_inner_configure)

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    def _login(self, identifier: str, password: str) -> None:
        self._identifier = identifier
        self.login_view.set_busy(True)
        self.login_view.clear_error()
        self.sidebar.set_connection("connecting")

        def work() -> None:
            try:
                outcome = self.client.login(identifier, password)
            except AeroError as exc:
                self.events.put(Event("login_error", exc))
                return
            if outcome.status == "otp_required":
                self.events.put(Event("login_otp", outcome))
                return
            self.events.put(Event("login_ok", outcome))

        import threading

        threading.Thread(target=work, name="grace-login", daemon=True).start()

    def _verify_otp(self, code: str) -> None:
        self.login_view.set_busy(True)
        self.login_view.clear_error()

        def work() -> None:
            try:
                outcome = self.client.verify_otp(self._identifier, code)
            except AeroError as exc:
                self.events.put(Event("login_error", exc))
                return
            self.events.put(Event("login_ok", outcome))

        import threading

        threading.Thread(target=work, name="grace-otp", daemon=True).start()

    def _cancel_otp(self) -> None:
        self.login_view.set_busy(False)
        self.login_view.clear_password()

    def _finish_login(self) -> None:
        self.login_view.pack_forget()
        self.login_view.set_busy(False)
        self.login_view.clear_password()
        self.sidebar.set_user(self.client.user)
        self.sidebar.set_connection("online")
        self._bootstrap_conversation()
        self.composer.focus_input()

    def _sign_out(self) -> None:
        if not messagebox.askyesno("Sign out", "Sign out of Aero Grace?"):
            return
        self.controller.shutdown()
        self.controller.reset()
        self.client.clear_token()
        self.chat.clear()
        self.chat.show_empty_state(self._use_suggestion)
        self.sidebar.set_user(None)
        self.sidebar.set_credits(None)
        self.sidebar.set_conversation(None)
        self.sidebar.set_connection("offline")
        self.header_title.configure(text=NEW_CONVERSATION_TITLE)
        self.composer.set_attachments([])
        self.login_view.clear_password()
        self.login_view.pack(fill="both", expand=True)
        self.login_view.set_busy(False)

    # ------------------------------------------------------------------ #
    # Conversation bootstrap
    # ------------------------------------------------------------------ #
    def _bootstrap_conversation(self) -> None:
        import threading

        self.sidebar.set_connection("connecting")

        def work() -> None:
            self.controller.bootstrap()

        threading.Thread(target=work, name="grace-bootstrap", daemon=True).start()

    # ------------------------------------------------------------------ #
    # Composer actions
    # ------------------------------------------------------------------ #
    def _send(self, text: str) -> None:
        if self.controller.busy:
            self._toast("Grace is still answering — wait or press Stop.", "warn")
            return
        if not text.strip():
            return
        if self.controller.attachments and self.controller.attachments.any_failed:
            self._toast("Fix or remove the failed attachment first.", "error")
            return
        self.composer.clear()
        self.controller.send(text)

    def _stop(self) -> None:
        self.controller.stop()

    def _attach(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Attach files to your message",
            parent=self.root,
        )
        if not paths:
            return
        problems = self.controller.add_attachments(list(paths))
        for problem in problems:
            self._toast(problem, "error")
        self.controller.upload_attachments()

    def _remove_attachment(self, attachment_id: str) -> None:
        self.controller.remove_attachment(attachment_id)

    def _retry_attachment(self, attachment_id: str) -> None:
        self.controller.retry_attachment(attachment_id)
        self._toast("Retrying upload…", "info")

    def _set_mode(self, key: str) -> None:
        self.controller.set_mode(key)

    def _use_suggestion(self, text: str) -> None:
        self.composer.set_text(text)
        self.composer.focus_input()

    # ------------------------------------------------------------------ #
    # Controller events -> UI
    # ------------------------------------------------------------------ #
    def _on_controller_event(self, event: Event) -> None:
        """Called from the controller's worker thread."""
        self.events.put(event)

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain)

    def _handle(self, event: Event) -> None:
        kind = event.kind
        if kind == "login_ok":
            self._finish_login()
        elif kind == "login_otp":
            self.login_view.set_busy(False)
            self.login_view.show_otp(event.data.message)
            self.sidebar.set_connection("offline")
        elif kind == "login_error":
            self._handle_login_error(event.data)
        elif kind == LOADING:
            self.sidebar.set_connection("connecting", str(event.data or "")[:40])
        elif kind == CONNECTION:
            self.sidebar.set_user(event.data)
        elif kind == CONVERSATION_READY:
            self._on_conversation_ready(event.data)
        elif kind == HISTORY_RESTORED:
            self._on_history_restored(event.data)
        elif kind == USER_MESSAGE:
            self._on_user_message(event.data)
        elif kind == ASSISTANT_START:
            self._on_assistant_start(event.data)
        elif kind == ASSISTANT_CHUNK:
            self._on_assistant_chunk(event.data)
        elif kind == STATUS:
            self._on_status(event.data)
        elif kind == ASSISTANT_DONE:
            self._on_assistant_done(event.data)
        elif kind == ASSISTANT_ERROR:
            self._on_assistant_error(event.data)
        elif kind == ERROR:
            self._on_error(event.data)
        elif kind == CREDITS:
            self._on_credits(event.data)
        elif kind == TITLE:
            self._on_title(event.data)
        elif kind == ATTACHMENT_CHANGED:
            self.composer.set_attachments(self.controller.attachments.items)
        elif kind == ATTACHMENTS_CLEARED:
            self.composer.set_attachments([])
        elif kind == BUSY:
            self.composer.set_busy(bool(event.data))
        elif kind == MODE_CHANGED:
            self.composer.set_mode(event.data)
            self.header_mode.configure(text=event.data.short_label)
        elif kind == "shutdown":
            pass

    # -- individual handlers ------------------------------------------- #
    def _handle_login_error(self, exc: AeroError) -> None:
        self.login_view.set_busy(False)
        self.sidebar.set_connection("offline")
        if getattr(exc, "code", "") in ("otp_required", "otp_rejected"):
            # Keep the user on the code step and explain what happened.
            if self.login_view.step != "otp":
                self.login_view.show_otp(exc.user_message)
            else:
                self.login_view.set_error(exc.user_message)
            return
        self.login_view.set_error(exc.user_message)
        self.login_view.clear_password()

    def _on_conversation_ready(self, conversation: Conversation) -> None:
        self.sidebar.set_conversation(conversation)
        self.header_title.configure(text=conversation.title)
        if not conversation.messages:
            self.chat.show_empty_state(self._use_suggestion)

    def _on_history_restored(self, conversation: Conversation) -> None:
        if conversation.messages:
            self.chat.render_conversation(conversation)
            self.chat.scroll_to_bottom()
            self._toast(
                f"Restored {len(conversation.messages)} messages from "
                f"“{conversation.title}”.",
                "info",
            )
        self.sidebar.set_connection("online")

    def _on_user_message(self, message: Message) -> None:
        self.chat.append_message(message)
        self.chat.auto_scroll()

    def _on_assistant_start(self, message: Message) -> None:
        self._stream_message = message
        bubble = self.chat.append_message(message)
        bubble.set_status("Grace is thinking…")
        self.chat.auto_scroll()

    def _on_assistant_chunk(self, message: Message) -> None:
        bubble = self.chat.bubble_for(message.id)
        if bubble is None:
            return
        bubble.set_streaming_text(message.content)
        bubble.set_status("")
        self.chat.auto_scroll()

    def _on_status(self, label: str) -> None:
        if self._stream_message is None:
            return
        bubble = self.chat.bubble_for(self._stream_message.id)
        if bubble is not None:
            bubble.set_status(label or "")

    def _on_assistant_done(self, payload) -> None:
        message, result = payload
        bubble = self.chat.bubble_for(message.id)
        if bubble is not None:
            bubble.finalize(result)
        self._stream_message = None
        self.sidebar.set_conversation(self.controller.conversation)
        self.header_title.configure(text=self.controller.title)
        self.chat.auto_scroll()

    def _on_assistant_error(self, message: Message) -> None:
        bubble = self.chat.bubble_for(message.id)
        if bubble is not None:
            bubble.mark_error()
        self._stream_message = None

    def _on_error(self, exc: AeroError) -> None:
        self._toast(exc.user_message, "error")
        log.info("user-facing error: %s", exc.code)

    def _on_credits(self, credits) -> None:
        self.sidebar.set_credits(credits)
        if credits.remaining is not None:
            self.header_credits.configure(text=f"{credits.remaining:g} credits")

    def _on_title(self, title: str) -> None:
        self.header_title.configure(text=title)
        self.sidebar.set_conversation(self.controller.conversation)

    # ------------------------------------------------------------------ #
    # Toast
    # ------------------------------------------------------------------ #
    def _toast(self, text: str, kind: str = "info") -> None:
        if self._pending_toast is not None:
            self._pending_toast.hide()
        toast = Toast(self.toast_host, text=text, kind=kind)
        self._pending_toast = toast
        toast.show()

    # ------------------------------------------------------------------ #
    # Fullscreen
    # ------------------------------------------------------------------ #
    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)

    def _leave_fullscreen(self) -> None:
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)

    # ------------------------------------------------------------------ #
    def _on_close(self) -> None:
        self.controller.shutdown()
        self.client.clear_token()
        self.root.destroy()

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        log.info("Aero Grace desktop starting")
        self.root.mainloop()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    debug = "--debug" in argv
    app = GraceApp(debug=debug)
    app.run()
    return 0
