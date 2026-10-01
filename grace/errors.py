"""Error taxonomy and user-facing copy.

Nothing in here is allowed to leak a raw traceback, a token, a password or a
URL that carries credentials.  ``AeroError.user_message`` is the only string
that ever reaches a dialog.
"""

from __future__ import annotations

import re
from typing import Optional


class AeroError(Exception):
    """Base class for every failure the client surfaces to a human."""

    #: Short, calm sentence shown to the user.
    user_message: str = "Something went wrong. Please try again."
    #: Machine readable code, safe to log.
    code: str = "unknown"
    #: True when retrying the exact same request could plausibly work.
    retryable: bool = False

    def __init__(self, detail: str = "", *, status: Optional[int] = None):
        super().__init__(detail or self.code)
        self.detail = _scrub(detail)
        self.status = status

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.code}: {self.detail}" if self.detail else self.code


_JWT_LIKE = re.compile(r"\beyJ[A-Za-z0-9._\-]{10,}\b")
_BEARER_LIKE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|token|otp)\s*[=:]\s*[^\s,;&\"\']+"
)
_LONG_OPAQUE = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b")


def _scrub(text: str) -> str:
    """Remove anything that looks like a credential from a detail string."""
    if not text:
        return ""
    cleaned = str(text)
    cleaned = _BEARER_LIKE.sub("Bearer [redacted]", cleaned)
    cleaned = _JWT_LIKE.sub("[redacted-jwt]", cleaned)
    cleaned = _SECRET_ASSIGNMENT.sub(r"\1=[redacted]", cleaned)
    cleaned = _LONG_OPAQUE.sub("[redacted]", cleaned)
    return cleaned[:600]


class NetworkUnavailable(AeroError):
    code = "network_unavailable"
    user_message = "Unable to connect to Grace. Check your connection and try again."
    retryable = True


class AuthFailure(AeroError):
    code = "auth_failed"
    user_message = "Your session could not be authenticated."


class InvalidCredentials(AuthFailure):
    """A 401 from the login endpoint specifically."""

    code = "invalid_credentials"
    user_message = "Invalid email/username or password."


class OtpRequired(AeroError):
    code = "otp_required"
    user_message = "This account needs a one-time code. Check your email."


class OtpRejected(AeroError):
    code = "otp_rejected"
    user_message = "That code was not accepted. Request a new one and try again."


class GraceServerError(AeroError):
    code = "server_error"
    user_message = "Grace returned an error. Please try again."
    retryable = True


class GraceRateLimited(AeroError):
    code = "rate_limited"
    user_message = "Grace is busy right now. Please wait a moment and try again."
    retryable = True


class GraceTimeout(AeroError):
    code = "timeout"
    user_message = "Grace took too long to respond."
    retryable = True


class GraceInterrupted(AeroError):
    code = "interrupted"
    user_message = "The connection to Grace dropped. The partial answer was kept."
    retryable = True


class AttachmentTooLarge(AeroError):
    code = "attachment_too_large"
    user_message = "That file is too large to attach."


class AttachmentUnsupported(AeroError):
    code = "attachment_unsupported"
    user_message = "That file type cannot be attached to a Grace message."


class AttachmentUploadFailed(AeroError):
    code = "attachment_upload_failed"
    user_message = "File upload failed. Retry or remove the attachment."
    retryable = True


class AttachmentQuotaExceeded(AeroError):
    code = "attachment_quota"
    user_message = "Too many attachments on one message."


class ConversationError(AeroError):
    code = "conversation_error"
    user_message = "Grace history could not be loaded. You can still start chatting."


class ModeRejected(AeroError):
    code = "mode_rejected"
    user_message = "Grace did not accept that mode. Switched back to Normal."
    retryable = True


# --------------------------------------------------------------------------- #
# Mapping from HTTP / transport failures onto the taxonomy
# --------------------------------------------------------------------------- #

def from_http_status(status: int, body: str = "") -> AeroError:
    """Translate an HTTP status into the closest taxonomy member."""
    text = (body or "")[:400]
    if status in (401, 403):
        return AuthFailure(text, status=status)
    if status == 404:
        return GraceServerError(f"HTTP 404 {text}", status=status)
    if status == 408:
        return GraceTimeout(f"HTTP 408 {text}", status=status)
    if status == 429:
        return GraceRateLimited(f"HTTP 429 {text}", status=status)
    if 500 <= status <= 599:
        return GraceServerError(f"HTTP {status} {text}", status=status)
    return GraceServerError(f"HTTP {status} {text}", status=status)


def from_exception(exc: BaseException) -> AeroError:
    """Translate a transport exception into the taxonomy."""
    name = type(exc).__name__
    if "Timeout" in name or "timed out" in str(exc).lower():
        return GraceTimeout(str(exc))
    if "Connection" in name or "ConnectionError" in name:
        return NetworkUnavailable(str(exc))
    if "SSLError" in name or "Certificate" in name:
        return NetworkUnavailable(str(exc))
    if "ChunkedEncoding" in name or "ProtocolError" in name:
        return GraceInterrupted(str(exc))
    return AeroError(str(exc))
