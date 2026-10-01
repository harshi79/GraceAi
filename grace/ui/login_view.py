"""Sign-in surface: identifier + password, then the OTP step when the
account has ``loginOtpEnabled``.

The password field is masked, the plaintext password never leaves this class
other than as the body of ``POST /api/auth/login``, and nothing is written to
disk.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from . import theme
from .widgets import Avatar, PillButton, ui_font

MASK = "•"


class LoginView(tk.Frame):
    """Two-step sign-in card."""

    def __init__(
        self,
        master,
        on_submit: Callable[[str, str], None],
        on_verify: Callable[[str], None],
        on_cancel: Callable[[], None],
        **kw,
    ):
        bg = kw.pop("background", theme.BG)
        super().__init__(master, bg=bg, **kw)
        self.on_submit = on_submit
        self.on_verify = on_verify
        self.on_cancel = on_cancel
        self._identifier = ""
        self._step = "credentials"

        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        center = tk.Frame(self, bg=theme.BG)
        center.pack(expand=True)

        Avatar(center, initials="G", size=52, background=theme.SURFACE).pack(pady=(0, 16))
        tk.Label(
            center, text="Aero · Grace", bg=theme.BG, fg=theme.TEXT,
            font=ui_font(theme.SIZE_XL, bold=True),
        ).pack()
        tk.Label(
            center, text="Sign in to continue to Grace", bg=theme.BG,
            fg=theme.TEXT_MUTED, font=ui_font(theme.SIZE_SM),
        ).pack(pady=(4, 22))

        self.card = tk.Frame(
            center, bg=theme.SURFACE_2,
            highlightbackground=theme.BORDER_2, highlightthickness=1, bd=0,
        )
        self.card.pack(ipadx=26, ipady=22)

        self._build_credentials()
        self._build_otp()

        self.error = tk.Label(
            center, text="", bg=theme.BG, fg=theme.DANGER,
            font=ui_font(theme.SIZE_SM), wraplength=340, justify="center",
        )
        self.error.pack(pady=(14, 0))

    # ------------------------------------------------------------------ #
    def _field(self, parent, label: str, secret: bool = False):
        tk.Label(
            parent, text=label, bg=theme.SURFACE_2, fg=theme.TEXT_MUTED,
            font=ui_font(theme.SIZE_XS), anchor="w",
        ).pack(fill="x", pady=(0, 4))
        entry = tk.Entry(
            parent,
            bg=theme.SURFACE_3,
            fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER_2,
            highlightcolor=theme.ACCENT,
            insertbackground=theme.ACCENT,
            show=MASK if secret else "",
            width=34,
        )
        entry.pack(fill="x", ipady=8)
        return entry

    def _build_credentials(self) -> None:
        frame = tk.Frame(self.card, bg=theme.SURFACE_2)
        self.credentials_frame = frame
        frame.pack(fill="both", expand=True)

        self.identifier = self._field(frame, "Email or username")
        self.password = self._field(frame, "Password", secret=True)

        self.password.bind("<Return>", lambda e: self._submit())
        self.identifier.bind("<Return>", lambda e: self.password.focus_set())

        self.submit = PillButton(
            frame, text="Sign in", command=self._submit, variant="accent",
            width=250, height=34, font_size=theme.SIZE_MD, bold=True,
            background=theme.SURFACE_2,
        )
        self.submit.pack(pady=(18, 0))

    def _build_otp(self) -> None:
        frame = tk.Frame(self.card, bg=theme.SURFACE_2)
        self.otp_frame = frame

        tk.Label(
            frame, text="Verification code", bg=theme.SURFACE_2, fg=theme.TEXT_MUTED,
            font=ui_font(theme.SIZE_XS), anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            frame,
            text="Enter the 6-digit code sent to your email.",
            bg=theme.SURFACE_2, fg=theme.TEXT_FAINT, font=ui_font(theme.SIZE_XS),
            anchor="w", wraplength=300, justify="left",
        ).pack(fill="x", pady=(0, 10))

        self.code = tk.Entry(
            frame, bg=theme.SURFACE_3, fg=theme.TEXT, font=ui_font(theme.SIZE_XL),
            relief="flat", bd=0, highlightthickness=1, highlightbackground=theme.BORDER_2,
            highlightcolor=theme.ACCENT, insertbackground=theme.ACCENT, width=34,
            justify="center",
        )
        self.code.pack(fill="x", ipady=8)
        self.code.bind("<Return>", lambda e: self._verify())
        self.code.bind("<KeyRelease>", lambda e: self._digits_only())

        row = tk.Frame(frame, bg=theme.SURFACE_2)
        row.pack(fill="x", pady=(16, 0))
        PillButton(
            row, text="Verify", command=self._verify, variant="accent",
            width=132, height=34, font_size=theme.SIZE_MD, bold=True,
            background=theme.SURFACE_2,
        ).pack(side="left")
        PillButton(
            row, text="Back", command=self._back, variant="subtle", width=104,
            height=34, font_size=theme.SIZE_SM, background=theme.SURFACE_2,
        ).pack(side="right")

    # ------------------------------------------------------------------ #
    def _digits_only(self) -> None:
        text = "".join(ch for ch in self.code.get() if ch.isdigit())[:6]
        if text != self.code.get():
            self.code.delete(0, "end")
            self.code.insert(0, text)

    # ------------------------------------------------------------------ #
    def _submit(self) -> None:
        identifier = self.identifier.get().strip()
        password = self.password.get()
        if not identifier or not password:
            self.set_error("Enter your email or username and your password.")
            return
        self._identifier = identifier
        self.clear_error()
        self.on_submit(identifier, password)

    def _verify(self) -> None:
        code = self.code.get().strip()
        if len(code) != 6:
            self.set_error("Enter the 6-digit code from your email.")
            return
        self.clear_error()
        self.on_verify(code)

    def _back(self) -> None:
        self._step = "credentials"
        self.otp_frame.pack_forget()
        self.credentials_frame.pack(fill="both", expand=True)
        self.clear_error()
        self.on_cancel()

    # ------------------------------------------------------------------ #
    def show_otp(self, message: str = "") -> None:
        self._step = "otp"
        self.credentials_frame.pack_forget()
        self.otp_frame.pack(fill="both", expand=True)
        self.clear_error()
        if message:
            self.set_info(message)
        self.code.focus_set()

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (self.submit,):
            widget.set_state(state)
        self.code.configure(state="normal" if not busy else "disabled")
        self.identifier.configure(state="normal" if not busy else "disabled")
        self.password.configure(state="normal" if not busy else "disabled")

    def set_error(self, message: str) -> None:
        self.error.configure(text=message, fg=theme.DANGER)

    def set_info(self, message: str) -> None:
        self.error.configure(text=message, fg=theme.TEXT_MUTED)

    def clear_error(self) -> None:
        self.error.configure(text="")

    def clear_password(self) -> None:
        self.password.delete(0, "end")

    @property
    def step(self) -> str:
        return self._step
