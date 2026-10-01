"""The composer: multiline input, attachments, mode picker, send/stop.

Keyboard contract (identical to the Aero web client and to ChatGPT):

* **Enter** sends
* **Shift+Enter** inserts a newline
* **Ctrl+Enter** / **Cmd+Enter** also sends
* an empty (or whitespace-only) composer never sends
* while a response is streaming the send button becomes a stop button and
  further sends are refused by the controller, not just by the widget
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional

from .. import modes
from ..attachments import format_size
from ..models import Attachment
from . import theme
from .widgets import IconButton, PillButton, SendButton, ui_font

PLACEHOLDER = "Message Grace…"
MAX_VISIBLE_LINES = 8
LINE_HEIGHT = 16


class ModePopup:
    """Borderless popup listing every Grace mode."""

    def __init__(self, master, on_pick: Callable[[str], None]):
        self.on_pick = on_pick
        self.top: Optional[tk.Toplevel] = None

    def show(self, widget: tk.Widget, current_key: str) -> None:
        self.hide()
        top = tk.Toplevel(widget, bg=theme.SURFACE_2, bd=0, highlightthickness=1,
                          highlightbackground=theme.BORDER_2)
        top.withdraw()
        top.overrideredirect(True)
        top.transient(widget.winfo_toplevel())
        self.top = top

        frame = tk.Frame(top, bg=theme.SURFACE_2, padx=4, pady=4)
        frame.pack(fill="both", expand=True)

        for mode in modes.ALL_MODES:
            row = tk.Frame(frame, bg=theme.SURFACE_2, cursor="hand2")
            row.pack(fill="x")
            selected = mode.key == current_key
            tk.Label(
                row, text=mode.short_label, bg=theme.SURFACE_2,
                fg=theme.TEXT if selected else theme.TEXT_MUTED,
                font=ui_font(theme.SIZE_SM, bold=selected), anchor="w", padx=10, pady=6,
                width=18,
            ).pack(side="left")
            tk.Label(
                row, text=mode.hint, bg=theme.SURFACE_2, fg=theme.TEXT_FAINT,
                font=ui_font(theme.SIZE_XS), anchor="w", padx=10, pady=6, width=26,
                wraplength=250, justify="left",
            ).pack(side="left", fill="x", expand=True)
            for w in (row, *row.winfo_children()):
                w.bind("<Button-1>", lambda e, k=mode.key: self._pick(k))
                w.bind("<Enter>", lambda e, r=row: _row_hover(r, True))
                w.bind("<Leave>", lambda e, r=row: _row_hover(r, False))

        top.update_idletasks()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() - top.winfo_height() - 6
        top.geometry(f"+{x}+{y}")
        top.deiconify()
        top.grab_set()
        top.focus_set()
        top.bind("<Escape>", lambda e: self.hide())
        top.bind("<FocusOut>", lambda e: self.hide())

    def _pick(self, key: str) -> None:
        self.hide()
        self.on_pick(key)

    def hide(self) -> None:
        if self.top is None:
            return
        try:
            self.top.grab_release()
        except Exception:  # pragma: no cover - defensive
            pass
        self.top.destroy()
        self.top = None


def _row_hover(row: tk.Frame, on: bool) -> None:
    bg = theme.SURFACE_3 if on else theme.SURFACE_2
    row.configure(bg=bg)
    for child in row.winfo_children():
        try:
            child.configure(bg=bg)
        except Exception:  # pragma: no cover - defensive
            pass


class Composer(tk.Frame):
    """Input surface pinned to the bottom of the chat area."""

    def __init__(
        self,
        master,
        on_send: Callable[[str], None],
        on_stop: Callable[[], None],
        on_attach: Callable[[], None],
        on_mode: Callable[[str], None],
        on_remove_attachment: Callable[[str], None],
        on_retry_attachment: Callable[[str], None],
        **kw,
    ):
        bg = kw.pop("background", theme.BG)
        super().__init__(master, bg=bg, **kw)
        self.on_send = on_send
        self.on_stop = on_stop
        self.on_attach = on_attach
        self.on_mode = on_mode
        self.on_remove_attachment = on_remove_attachment
        self.on_retry_attachment = on_retry_attachment
        self._busy = False
        self._mode = modes.default()
        self._attachments: List[Attachment] = []

        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        outer = tk.Frame(self, bg=theme.BG)
        outer.pack(fill="x", padx=18, pady=(4, 14))

        # ---- attachment chips ---------------------------------------- #
        self.chips = tk.Frame(outer, bg=theme.BG)
        self.chips.pack(fill="x")

        # ---- input card ---------------------------------------------- #
        card = tk.Frame(
            outer, bg=theme.SURFACE_2,
            highlightbackground=theme.BORDER_2, highlightthickness=1, bd=0,
        )
        card.pack(fill="x", pady=(8, 0))

        self.input = tk.Text(
            card,
            wrap="word",
            bg=theme.SURFACE_2,
            fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD),
            relief="flat",
            bd=0,
            padx=14,
            pady=11,
            highlightthickness=0,
            insertbackground=theme.ACCENT,
            height=1,
            undo=False,
            maxundo=-1,
            exportselection=False,
        )
        self.input.pack(fill="x", expand=True)
        self._placeholder_on = True
        self._show_placeholder()
        self.input.bind("<FocusIn>", lambda e: self._on_focus(True))
        self.input.bind("<FocusOut>", lambda e: self._on_focus(False))
        self.input.bind("<KeyRelease>", self._on_key_release)
        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", self._on_shift_return)
        self.input.bind("<Control-Return>", self._on_ctrl_return)

        # ---- button row ---------------------------------------------- #
        row = tk.Frame(card, bg=theme.SURFACE_2)
        row.pack(fill="x", padx=10, pady=(0, 9))

        self.attach_button = IconButton(
            row, glyph="+", command=self.on_attach, size=30, background=theme.SURFACE_2,
        )
        self.attach_button.pack(side="left")

        self.mode_button = PillButton(
            row, text=self._mode.short_label, command=self._open_modes,
            variant="subtle", width=132, height=30, font_size=theme.SIZE_SM,
            background=theme.SURFACE_2, radius=15,
        )
        self.mode_button.pack(side="left", padx=(8, 0))

        hint = tk.Label(
            row, text="Enter to send · Shift+Enter for a new line", bg=theme.SURFACE_2,
            fg=theme.TEXT_FAINT, font=ui_font(theme.SIZE_XS),
        )
        hint.pack(side="left", padx=(14, 0))

        self.stop_button = PillButton(
            row, text="Stop", command=self.on_stop, variant="danger", width=62,
            height=30, font_size=theme.SIZE_SM, background=theme.SURFACE_2, radius=15,
        )
        self.send_button = SendButton(row, command=self._send, diameter=32,
                                      background=theme.SURFACE_2)
        self.send_button.pack(side="right")
        self.send_button.set_enabled(False)

        self.mode_popup = ModePopup(self, on_pick=self._pick_mode)

        # ---- footer note --------------------------------------------- #
        tk.Label(
            outer,
            text="Grace can make mistakes. Your conversations are private and encrypted.",
            bg=theme.BG, fg=theme.TEXT_FAINT, font=ui_font(theme.SIZE_XS),
        ).pack(pady=(8, 0))

    # ------------------------------------------------------------------ #
    # Placeholder
    # ------------------------------------------------------------------ #
    def _show_placeholder(self) -> None:
        if self._placeholder_on:
            return
        self._placeholder_on = True
        self.input.delete("1.0", "end")
        self.input.configure(fg=theme.TEXT_FAINT)
        self.input.insert("1.0", PLACEHOLDER)

    def _clear_placeholder(self) -> None:
        if not self._placeholder_on:
            return
        self._placeholder_on = False
        self.input.delete("1.0", "end")
        self.input.configure(fg=theme.TEXT)

    def _on_focus(self, focused: bool) -> None:
        if focused:
            self._clear_placeholder()
            self._autosize()
        elif not self.get_text().strip():
            self._show_placeholder()

    # ------------------------------------------------------------------ #
    # Text helpers
    # ------------------------------------------------------------------ #
    def get_text(self) -> str:
        if self._placeholder_on:
            return ""
        return self.input.get("1.0", "end - 1 char")

    def set_text(self, text: str) -> None:
        if text:
            self._clear_placeholder()
            self.input.delete("1.0", "end")
            self.input.insert("1.0", text)
        else:
            self._show_placeholder()
        self._autosize()

    def clear(self) -> None:
        self.set_text("")
        self.input.see("1.0")

    def focus_input(self) -> None:
        self.input.focus_set()

    def _on_key_release(self, _event=None) -> None:
        self._autosize()
        self._refresh_send_state()

    def _autosize(self) -> None:
        if self._placeholder_on:
            self.input.configure(height=1)
            return
        try:
            displayed = int(
                self.input.count("1.0", "end - 1 char", "displaylines") or 1
            )
        except Exception:  # pragma: no cover - defensive
            displayed = 1
        self.input.configure(height=max(1, min(displayed, MAX_VISIBLE_LINES)))

    # ------------------------------------------------------------------ #
    # Keyboard
    # ------------------------------------------------------------------ #
    def _on_return(self, event) -> str:
        if event.state & 0x1:  # Shift held -> newline
            return self._on_shift_return(event)
        self._send()
        return "break"

    def _on_shift_return(self, event) -> str:
        if self._placeholder_on:
            self._clear_placeholder()
        self._autosize()
        return ""  # let Tk insert the newline

    def _on_ctrl_return(self, event) -> str:
        self._send()
        return "break"

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #
    def _send(self) -> None:
        text = self.get_text().strip()
        if not text or self._busy:
            return
        self.on_send(text)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.send_button.pack_forget()
            self.stop_button.pack(side="right")
        else:
            self.stop_button.pack_forget()
            self.send_button.pack(side="right")
        self._refresh_send_state()

    def _refresh_send_state(self) -> None:
        if self._busy:
            self.send_button.set_enabled(False)
            self.attach_button.set_state("disabled")
        else:
            ready = bool(self.get_text().strip()) and not self._attachments_blocked()
            self.send_button.set_enabled(ready)
            self.attach_button.set_state("normal")

    def _attachments_blocked(self) -> bool:
        return any(a.state == "uploading" for a in self._attachments)

    # ------------------------------------------------------------------ #
    # Attachments
    # ------------------------------------------------------------------ #
    def set_attachments(self, attachments: List[Attachment]) -> None:
        self._attachments = list(attachments)
        for child in self.chips.winfo_children():
            child.destroy()
        for attachment in self._attachments:
            self._chip(attachment)
        self._refresh_send_state()

    def _chip(self, attachment: Attachment) -> None:
        chip = tk.Frame(
            self.chips, bg=theme.SURFACE_2,
            highlightbackground=theme.BORDER_2, highlightthickness=1, bd=0,
        )
        chip.pack(side="left", padx=(0, 8), pady=(0, 4))

        body = tk.Frame(chip, bg=theme.SURFACE_2)
        body.pack(side="left", padx=(10, 4), pady=6)

        state_color = {
            "pending": theme.TEXT_MUTED,
            "uploading": theme.WARN,
            "uploaded": theme.SUCCESS,
            "failed": theme.DANGER,
        }.get(attachment.state, theme.TEXT_MUTED)

        name = tk.Label(
            body, text=attachment.name, bg=theme.SURFACE_2, fg=theme.TEXT,
            font=ui_font(theme.SIZE_XS), anchor="w",
        )
        name.pack(anchor="w")

        if attachment.state == "uploading":
            detail = f"Uploading {int(attachment.progress * 100)}%"
        elif attachment.state == "uploaded":
            detail = format_size(attachment.size)
        elif attachment.state == "failed":
            detail = attachment.error or "Upload failed"
        else:
            detail = format_size(attachment.size)
        tk.Label(
            body, text=detail, bg=theme.SURFACE_2, fg=state_color,
            font=ui_font(theme.SIZE_XS), anchor="w",
        ).pack(anchor="w")

        action_text = "Retry" if attachment.state == "failed" else "×"
        action = tk.Label(
            chip, text=action_text, bg=theme.SURFACE_2, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS, bold=True), cursor="hand2", padx=8,
        )
        action.pack(side="right", fill="y")
        if attachment.state == "failed":
            action.bind("<Button-1>", lambda e, a=attachment: self.on_retry_attachment(a.id))
        else:
            action.bind("<Button-1>", lambda e, a=attachment: self.on_remove_attachment(a.id))
        action.bind("<Enter>", lambda e, w=action: w.configure(fg=theme.TEXT))
        action.bind("<Leave>", lambda e, w=action: w.configure(fg=theme.TEXT_FAINT))

    # ------------------------------------------------------------------ #
    # Mode
    # ------------------------------------------------------------------ #
    def _open_modes(self) -> None:
        self.mode_popup.show(self.mode_button, self._mode.key)

    def _pick_mode(self, key: str) -> None:
        self.set_mode(modes.get(key))
        self.on_mode(key)

    def set_mode(self, mode) -> None:
        self._mode = mode
        self.mode_button.set_text(mode.short_label)
