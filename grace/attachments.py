"""Attachment policy, validation and upload lifecycle.

This module owns the *state machine* only - no tkinter.  The UI subscribes to
the callbacks and paints chips/progress; everything testable lives here.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, List, Optional, Tuple

from . import config
from .errors import AeroError
from .logutil import log
from .models import Attachment, new_id

Callback = Callable[[Attachment], None]


class AttachmentManager:
    """Validate, upload and track the files attached to a pending message."""

    def __init__(
        self,
        uploader: Optional[Callable[[str, Callable[[float], None]], Attachment]] = None,
        policy: Optional[config.AttachmentPolicy] = None,
        on_change: Optional[Callback] = None,
        on_error: Optional[Callable[[Attachment, str], None]] = None,
    ) -> None:
        self._policy = policy or config.DEFAULT_ATTACHMENT_POLICY
        self._uploader = uploader
        self._on_change = on_change
        self._on_error = on_error
        self._items: List[Attachment] = []
        self._lock = threading.RLock()
        self._busy = False

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def items(self) -> List[Attachment]:
        with self._lock:
            return list(self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __bool__(self) -> bool:
        return len(self) > 0

    @property
    def all_ready(self) -> bool:
        with self._lock:
            return bool(self._items) and all(i.ready for i in self._items)

    @property
    def any_failed(self) -> bool:
        with self._lock:
            return any(i.state == "failed" for i in self._items)

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def ready_references(self) -> List[str]:
        with self._lock:
            return [i.remote_id for i in self._items if i.ready and i.remote_id]

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self, path: str) -> Optional[Tuple[str, str]]:
        """Return ``(code, message)`` when ``path`` is not acceptable."""
        if not os.path.isfile(path):
            return ("missing", "That file no longer exists.")
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        if ext in self._policy.blocked_extensions:
            return ("blocked", f"{ext or name} files cannot be attached.")
        if ext and ext not in self._policy.extensions:
            return ("unsupported", f"{ext} files are not supported.")
        if not ext:
            return ("unsupported", "Files without an extension are not supported.")
        try:
            size = os.path.getsize(path)
        except OSError:
            return ("unreadable", "That file could not be read.")
        if size <= 0:
            return ("empty", "That file is empty.")
        if size > self._policy.max_bytes:
            return (
                "too_large",
                f"{name} is too large ({_human(size)}). "
                f"The limit is {_human(self._policy.max_bytes)}.",
            )
        with self._lock:
            if any(i.path == os.path.abspath(path) for i in self._items):
                return ("duplicate", f"{name} is already attached.")
            if len(self._items) >= self._policy.max_count:
                return ("quota", f"You can attach up to {self._policy.max_count} files.")
        return None

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def add_paths(self, paths: List[str]) -> Tuple[List[Attachment], List[str]]:
        """Add files, returning the accepted attachments and error strings."""
        added: List[Attachment] = []
        problems: List[str] = []
        for path in paths:
            problem = self.validate(path)
            if problem:
                problems.append(problem[1])
                continue
            name = os.path.basename(path)
            attachment = Attachment(
                id=new_id("att_"),
                path=os.path.abspath(path),
                name=name,
                size=os.path.getsize(path),
                mime="",
                state="pending",
            )
            with self._lock:
                self._items.append(attachment)
            added.append(attachment)
            self._notify(attachment)
        return added, problems

    def remove(self, attachment_id: str) -> None:
        with self._lock:
            self._items = [i for i in self._items if i.id != attachment_id]
        self._notify(None)

    def clear(self) -> None:
        with self._lock:
            self._items = []
        self._notify(None)

    def retry(self, attachment_id: str) -> None:
        with self._lock:
            target = next((i for i in self._items if i.id == attachment_id), None)
        if target is None or target.state != "failed":
            return
        self._upload(target)

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #
    def upload_all(self) -> None:
        """Upload every pending attachment (idempotent, thread safe)."""
        with self._lock:
            if self._busy:
                return
            self._busy = True
            pending = [i for i in self._items if i.state == "pending"]
        try:
            for attachment in pending:
                self._upload(attachment)
        finally:
            with self._lock:
                self._busy = False

    def _upload(self, attachment: Attachment) -> None:
        if self._uploader is None:
            attachment.state = "failed"
            attachment.error = "Upload is not configured."
            self._notify(attachment)
            if self._on_error:
                self._on_error(attachment, attachment.error)
            return

        attachment.state = "uploading"
        attachment.progress = 0.0
        attachment.attempts += 1
        attachment.error = ""
        self._notify(attachment)

        def _progress(fraction: float) -> None:
            attachment.progress = max(0.0, min(1.0, fraction))
            self._notify(attachment)

        try:
            uploaded = self._uploader(attachment.path, _progress)
        except AeroError as exc:
            attachment.state = "failed"
            attachment.error = exc.user_message
            self._notify(attachment)
            if self._on_error:
                self._on_error(attachment, attachment.error)
            return
        except Exception as exc:  # pragma: no cover - defensive
            attachment.state = "failed"
            attachment.error = "Upload failed unexpectedly."
            self._notify(attachment)
            log.debug("attachment upload error: %s", type(exc).__name__)
            if self._on_error:
                self._on_error(attachment, attachment.error)
            return

        attachment.state = uploaded.state
        attachment.progress = 1.0
        attachment.remote_id = uploaded.remote_id
        attachment.mime = uploaded.mime or attachment.mime
        self._notify(attachment)

    # ------------------------------------------------------------------ #
    def _notify(self, attachment: Optional[Attachment]) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(attachment)
        except Exception:  # pragma: no cover - defensive
            log.exception("attachment change callback failed")


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def format_size(size: int) -> str:
    return _human(size)
