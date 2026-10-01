"""Error taxonomy: friendly copy, no tracebacks, no credential leakage."""

from __future__ import annotations

import traceback

import pytest
import requests

from grace.errors import (
    AeroError,
    AttachmentTooLarge,
    AttachmentUnsupported,
    AuthFailure,
    GraceInterrupted,
    GraceRateLimited,
    GraceServerError,
    GraceTimeout,
    InvalidCredentials,
    NetworkUnavailable,
    from_exception,
    from_http_status,
)


def every_error():
    return [
        NetworkUnavailable(),
        AuthFailure(),
        InvalidCredentials(),
        GraceServerError(),
        GraceRateLimited(),
        GraceTimeout(),
        GraceInterrupted(),
        AttachmentTooLarge(),
        AttachmentUnsupported(),
        AeroError(),
    ]


@pytest.mark.parametrize("exc", every_error())
def test_every_error_has_calm_user_copy(exc):
    message = exc.user_message
    assert message
    assert "Traceback" not in message
    assert "File \"" not in message
    assert "line " not in message.lower() or "new line" in message.lower()
    # No raw internals.
    for banned in ("requests.", "socket.", "0x", "None", "{}", "[]"):
        assert banned not in message


@pytest.mark.parametrize("exc", every_error())
def test_every_error_has_a_code(exc):
    assert exc.code and exc.code.islower()
    assert " " not in exc.code


def test_str_never_contains_a_token():
    exc = GraceServerError("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdef")
    assert "eyJhbGciOiJIUzI1NiJ9" not in str(exc)
    assert "[redacted]" in str(exc)


def test_detail_is_scrubbed():
    exc = AeroError("password=hunter2 token=abcdef0123456789abcdef0123456789")
    assert "hunter2" not in exc.detail
    assert "abcdef0123456789abcdef0123456789" not in exc.detail


def test_http_status_mapping():
    assert isinstance(from_http_status(401), AuthFailure)
    assert isinstance(from_http_status(403), AuthFailure)
    assert isinstance(from_http_status(429), GraceRateLimited)
    assert isinstance(from_http_status(408), GraceTimeout)
    assert isinstance(from_http_status(500), GraceServerError)
    assert isinstance(from_http_status(503), GraceServerError)
    assert isinstance(from_http_status(404), GraceServerError)


def test_exception_mapping():
    assert isinstance(from_exception(requests.ConnectionError("x")), NetworkUnavailable)
    assert isinstance(from_exception(requests.Timeout("x")), GraceTimeout)
    assert isinstance(from_exception(requests.exceptions.SSLError("x")), NetworkUnavailable)
    assert isinstance(
        from_exception(requests.exceptions.ChunkedEncodingError("x")), GraceInterrupted
    )
    assert isinstance(from_exception(ValueError("x")), AeroError)


def test_retryable_flags_are_sensible():
    assert NetworkUnavailable().retryable is True
    assert GraceRateLimited().retryable is True
    assert GraceServerError().retryable is True
    assert InvalidCredentials().retryable is False
    assert AuthFailure().retryable is False


def test_error_detail_is_truncated():
    exc = AeroError("x" * 5000)
    assert len(exc.detail) <= 600


def test_no_traceback_is_ever_formatted_into_user_copy():
    try:
        raise RuntimeError("kaboom")
    except RuntimeError:
        formatted = traceback.format_exc()
    exc = AeroError(formatted)
    assert "Traceback" not in exc.user_message
    assert "RuntimeError" not in exc.user_message
