"""Logging that never writes a credential.

Rules enforced here:
* the access token, the password and the OTP code are never formatted into a
  record, at any level;
* the ``Authorization`` header is replaced before a request is logged;
* query strings and URLs are reduced to ``scheme://host/path``;
* anything that still looks like a bearer token or an email/password pair is
  scrubbed by :func:`redact` as a final safety net.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

LOGGER_NAME = "grace"

_SECRET_KEYS = re.compile(
    r"(?i)\b(password|passwd|pwd|token|accesstoken|access_token|refresh[_-]?token|"
    r"secret|authorization|auth[_-]?header|otp|code|api[_-]?key|apikey|"
    r"set-cookie|cookie|session|signature|sig|credential)\b"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9._\-]{10,}\b")
_URL_QUERY = re.compile(r"([a-z][a-z0-9+.\-]*://[^/\s?#]+[^?\s]*)\?[^\s]*")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|token|otp)\s*[=:]\s*[^\s,;&\"\'%]+"
)
_LONG_OPAQUE = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")


def redact(value: Any) -> str:
    """Return ``value`` as a string with anything credential-shaped removed."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _JWT.sub("[redacted-jwt]", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1=[redacted]", text)
    text = _URL_QUERY.sub(r"\1?[redacted]", text)
    text = _EMAIL.sub("[redacted-email]", text)
    text = _LONG_OPAQUE.sub("[redacted]", text)
    return text


def redact_mapping(mapping: Any) -> Any:
    """Recursively copy ``mapping`` replacing secret-looking values."""
    if isinstance(mapping, dict):
        out = {}
        for key, val in mapping.items():
            if isinstance(key, str) and _SECRET_KEYS.search(key):
                out[key] = "[redacted]"
            else:
                out[key] = redact_mapping(val)
        return out
    if isinstance(mapping, (list, tuple)):
        return [redact_mapping(v) for v in mapping]
    if isinstance(mapping, str):
        return redact(mapping)
    return mapping


def safe_headers(headers: Any) -> dict:
    """Copy of a header mapping with the auth header removed."""
    try:
        items = dict(headers).items()
    except Exception:  # pragma: no cover - defensive
        return {}
    return {
        str(k): ("[redacted]" if _SECRET_KEYS.search(str(k)) else str(v))
        for k, v in items
    }


def safe_url(url: str) -> str:
    """``scheme://host/path`` with any query string stripped."""
    return _URL_QUERY.sub(r"\1?[redacted]", str(url))


class RedactingFilter(logging.Filter):
    """Last line of defence: scrub every formatted record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = redact_mapping(record.args)
                else:
                    # Only strings are rewritten: %d/%f args must stay numeric.
                    record.args = tuple(
                        redact(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:  # pragma: no cover - never break logging
            pass
        return True


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return the application logger with redaction installed."""
    logger = logging.getLogger(name)
    if getattr(logger, "_grace_configured", False):
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.addFilter(RedactingFilter())
    logger._grace_configured = True  # type: ignore[attr-defined]
    return logger


def enable_debug() -> None:
    """Turn on DEBUG logging (still fully redacted)."""
    get_logger().setLevel(logging.DEBUG)


log = get_logger()
