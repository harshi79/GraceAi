"""Nothing credential-shaped may reach a log record or the console."""

from __future__ import annotations

import logging

from grace import logutil
from grace.logutil import RedactingFilter, redact, redact_mapping, safe_headers, safe_url

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret-payload-here.signature"
PASSWORD = "correct-horse-battery-staple"


def test_bearer_tokens_are_redacted():
    out = redact(f"Authorization: Bearer {TOKEN}")
    assert TOKEN not in out
    assert "[redacted]" in out


def test_jwt_shaped_strings_are_redacted():
    assert TOKEN not in redact(TOKEN)


def test_emails_are_redacted():
    assert "ada@example.com" not in redact("user is ada@example.com")


def test_query_strings_are_redacted():
    out = redact("https://api.example.com/api/auth/login?token=abc&sig=1")
    assert "token=abc" not in out
    assert "api.example.com/api/auth/login" in out


def test_long_opaque_strings_are_redacted():
    out = redact("session=" + "a" * 48)
    assert "a" * 48 not in out


def test_secret_keys_are_redacted_in_mappings():
    cleaned = redact_mapping(
        {"password": PASSWORD, "accessToken": TOKEN, "message": "hello"}
    )
    assert cleaned["password"] == "[redacted]"
    assert cleaned["accessToken"] == "[redacted]"
    assert cleaned["message"] == "hello"


def test_nested_mappings_are_redacted():
    cleaned = redact_mapping({"outer": {"token": TOKEN, "keep": 1}})
    assert cleaned["outer"]["token"] == "[redacted]"
    assert cleaned["outer"]["keep"] == 1


def test_authorization_header_is_redacted():
    headers = safe_headers({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    assert TOKEN not in headers["Authorization"]
    assert headers["Accept"] == "application/json"


def test_safe_url_strips_the_query():
    assert safe_url("https://api.example.com/x?token=1") == (
        "https://api.example.com/x?[redacted]"
    )


def test_logging_filter_scrubs_records():
    record = logging.LogRecord(
        "grace", logging.INFO, __file__, 1,
        "sending Authorization: Bearer %s", (TOKEN,), None,
    )
    RedactingFilter().filter(record)
    assert TOKEN not in record.getMessage()


def test_logging_filter_scrubs_dict_args():
    record = logging.LogRecord(
        "grace", logging.INFO, __file__, 1,
        "login %(identifier)s %(password)s", (), None,
    )
    record.args = {"identifier": "ada", "password": PASSWORD}
    RedactingFilter().filter(record)
    assert PASSWORD not in record.getMessage()


def test_logger_output_is_redacted(caplog):
    """The realistic path: the caller redacts before logging."""
    logger = logutil.get_logger("grace")
    logger.propagate = True
    with caplog.at_level(logging.INFO, logger="grace"):
        logger.info(
            "POST /api/auth/login payload=%s",
            redact_mapping({"identifier": "ada", "password": PASSWORD,
                            "accessToken": TOKEN}),
        )
    text = caplog.text
    assert TOKEN not in text
    assert PASSWORD not in text
    assert "[redacted]" in text


def test_logger_scrubs_a_token_pasted_into_the_message(caplog):
    logger = logutil.get_logger("grace")
    logger.propagate = True
    with caplog.at_level(logging.INFO, logger="grace"):
        logger.info("Authorization: Bearer %s", TOKEN)
    assert TOKEN not in caplog.text


def test_logger_is_singleton():
    assert logutil.get_logger("grace") is logutil.get_logger("grace")


def test_redact_handles_non_strings():
    assert redact(None) == ""
    assert redact(12) == "12"
    assert redact(b"bytes") == "b'bytes'"


def test_secret_assignments_are_redacted():
    out = redact("login with password=hunter2 and api_key=abcd1234")
    assert "hunter2" not in out
    assert "abcd1234" not in out


def test_plain_messages_are_untouched():
    assert redact("Grace is thinking…") == "Grace is thinking…"
