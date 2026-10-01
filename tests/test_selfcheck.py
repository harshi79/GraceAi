"""The `--check` startup self-report."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grace import config, selfcheck  # noqa: E402


def test_every_check_runs_without_raising():
    for check in selfcheck.CHECKS:
        name, passed, detail = check()
        assert isinstance(name, str) and name
        assert isinstance(passed, bool)
        assert isinstance(detail, str)


def test_expected_checks_are_registered():
    names = [c.__name__ for c in selfcheck.CHECKS]
    assert names == [
        "check_python",
        "check_requests",
        "check_core_imports",
        "check_gui_imports",
        "check_https",
        "check_sse",
        "check_markdown",
        "check_modes",
        "check_attachments",
        "check_no_credentials_on_disk",
    ]


def test_core_imports_check_passes():
    name, passed, detail = selfcheck.check_core_imports()
    assert name == "core modules"
    assert passed, detail


def test_https_check_passes():
    assert selfcheck.check_https()[1] is True


def test_sse_check_passes():
    assert selfcheck.check_sse()[1] is True


def test_markdown_check_passes():
    assert selfcheck.check_markdown()[1] is True


def test_modes_check_passes():
    assert selfcheck.check_modes()[1] is True


def test_attachments_check_passes():
    assert selfcheck.check_attachments()[1] is True


def test_credential_scan_passes_on_a_clean_tree():
    name, passed, detail = selfcheck.check_no_credentials_on_disk()
    assert passed, detail


def test_credential_scan_ignores_the_test_fixtures():
    """tests/ holds deliberate fake credentials; they must not trip the scan."""
    assert selfcheck.check_no_credentials_on_disk()[1] is True
    with open("tests/test_redaction.py", "r", encoding="utf-8") as handle:
        assert "correct-horse-battery-staple" in handle.read()


def test_gui_check_reports_tkinter_status():
    name, passed, detail = selfcheck.check_gui_imports()
    assert name in ("tkinter", "gui modules")
    if not passed:
        assert "python3-tk" in detail or "tk" in detail


def test_https_check_catches_a_plaintext_origin(monkeypatch):
    monkeypatch.setattr(config, "API_ORIGIN", "http://insecure.example.com")
    name, passed, detail = selfcheck.check_https()
    assert passed is False
    assert "insecure.example.com" in detail


def test_python_check_reports_the_running_version():
    name, passed, detail = selfcheck.check_python()
    assert passed is True
    assert detail.startswith("3.")


def test_selfcheck_returns_zero_on_this_machine(capsys):
    code = selfcheck.run_selfcheck()
    out = capsys.readouterr().out
    assert code == 0, out
    assert "All 10 checks passed." in out
    # tkinter may be missing here; that must not be a hard failure.
    assert "blocking" not in out


def test_selfcheck_verbose_prints_the_contract_report(capsys):
    selfcheck.run_selfcheck(verbose=True)
    out = capsys.readouterr().out
    assert "/ai/grace/respond" in out
    assert "inferred" in out
    assert "Normal · Thinking" in out


def test_selfcheck_main_accepts_verbose(capsys):
    assert selfcheck.main(["-v"]) == 0
    assert "Endpoints:" in capsys.readouterr().out


def test_main_without_arguments(capsys):
    assert selfcheck.main([]) == 0
    assert "Aero Grace desktop" in capsys.readouterr().out
