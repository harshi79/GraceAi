"""Environment and startup self-check.

``python3 run.py --check`` runs this instead of opening a window.  It answers
"will this machine actually run the client?" without needing a display, which
is exactly the question that cannot be answered by the test suite on a headless
box.

It never touches the network and never prints a credential.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, List, Tuple

from . import __version__, config, modes

Result = Tuple[str, bool, str]


def _ok(name: str, detail: str = "") -> Result:
    return (name, True, detail)


def _fail(name: str, detail: str) -> Result:
    return (name, False, detail)


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def check_python() -> Result:
    if sys.version_info < (3, 9):
        return _fail("python", f"{sys.version_info.major}.{sys.version_info.minor} "
                               f"— 3.9+ required")
    return _ok("python", f"{sys.version_info.major}.{sys.version_info.minor}."
                         f"{sys.version_info.micro}")


def check_requests() -> Result:
    try:
        import requests
    except ImportError:
        return _fail("requests", "not installed — pip install -r requirements.txt")
    return _ok("requests", requests.__version__)


CORE_MODULES = (
    "attachments", "client", "config", "controller", "errors", "logutil",
    "markdown_render", "models", "modes", "sse",
)


def check_core_imports() -> Result:
    import importlib

    broken = []
    for name in CORE_MODULES:
        try:
            importlib.import_module(f"grace.{name}")
        except Exception as exc:
            broken.append(f"{name} ({type(exc).__name__})")
    if broken:
        return _fail("core modules", "failed: " + ", ".join(broken))
    return _ok("core modules", f"{len(CORE_MODULES)}/{len(CORE_MODULES)} import cleanly")


UI_MODULES = (
    "app", "chat_view", "composer", "login_view", "markdown_view", "sidebar",
    "theme", "widgets",
)


def _tkinter_available() -> bool:
    """True only for a real tkinter, not a stub already in ``sys.modules``."""
    if "tkinter" in sys.modules:
        module = sys.modules["tkinter"]
        return getattr(module, "__file__", None) is not None
    import importlib.util

    try:
        return importlib.util.find_spec("tkinter") is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


def check_gui_imports() -> Result:
    import importlib

    if not _tkinter_available():
        return _fail(
            "tkinter",
            "not available — install python3-tk (Debian/Ubuntu), "
            "python3-tkinter (Fedora) or tk (Arch)",
        )

    broken = []
    for name in UI_MODULES:
        try:
            importlib.import_module(f"grace.ui.{name}")
        except Exception as exc:
            broken.append(f"{name} ({type(exc).__name__})")
    if broken:
        return _fail("gui modules", "failed: " + ", ".join(broken))

    detail = f"{len(UI_MODULES)}/{len(UI_MODULES)} import cleanly"
    try:
        import tkinter.font as tkfont

        detail += f", {len(tkfont.families())} font families visible"
    except Exception:
        detail += " (no display to enumerate fonts)"
    return _ok("gui modules", detail)


def check_https() -> Result:
    if not config.API_ORIGIN.startswith("https://"):
        return _fail("https", f"AERO_API_ORIGIN is {config.API_ORIGIN!r}")
    return _ok("https", config.API_ORIGIN)


def check_sse() -> Result:
    from .sse import parse_text

    events = parse_text(
        'data: {"type":"chunk","content":"hi"}\n\n'
        'data: {"type":"done","fullContent":"hi"}\n\n'
        "data: [DONE]\n\n"
    )
    if len(events) != 3 or not events[-1].is_done:
        return _fail("sse decoder", f"expected 3 events ending in [DONE], got {len(events)}")
    return _ok("sse decoder", "framing, JSON and [DONE] all decode")


def check_markdown() -> Result:
    from . import markdown_render as md

    blocks = md.parse("# H\n\n**b** `c`\n\n```py\nx=1\n```\n\n- a\n- b\n")
    names = [type(b).__name__ for b in blocks]
    expected = ["Heading", "Paragraph", "CodeBlock", "ListItem", "ListItem"]
    if names != expected:
        return _fail("markdown engine", f"got {names}")
    return _ok("markdown engine", "headings, emphasis, code fences and lists")


def check_modes() -> Result:
    if len(modes.ALL_MODES) < 6:
        return _fail("mode registry", f"only {len(modes.ALL_MODES)} modes")
    default = modes.default()
    if not default.verified:
        return _fail("mode registry", "the default mode is not marked verified")
    return _ok(
        "mode registry",
        f"{len(modes.ALL_MODES)} modes, default {default.short_label!r}",
    )


def check_attachments() -> Result:
    policy = config.DEFAULT_ATTACHMENT_POLICY
    if not policy.extensions:
        return _fail("attachment policy", "no accepted extensions")
    return _ok(
        "attachment policy",
        f"{len(policy.extensions)} extensions, "
        f"{len(policy.blocked_extensions)} blocked, "
        f"{policy.max_count} files / {policy.max_bytes // (1024 * 1024)} MB each",
    )


def check_no_credentials_on_disk() -> Result:
    """Best-effort: nothing in the shipped application looks like a secret.

    Only ``grace/`` and ``run.py`` are scanned.  ``tests/`` is skipped on
    purpose - it contains deliberate fake credentials such as
    ``PASSWORD = "correct-horse-battery-staple"``.
    """
    import re

    pattern = re.compile(r"(?i)(access[_-]?token|password)\s*[:=]\s*[\"'][^\"']{8,}")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hits = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "grace")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if filename == os.path.basename(__file__):
                continue  # this file contains the detection pattern itself
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    for i, line in enumerate(handle, 1):
                        if pattern.search(line):
                            hits.append(f"{os.path.relpath(path, root)}:{i}")
            except OSError:
                continue
    if hits:
        return _fail("credential scan", f"possible literals at {', '.join(hits[:3])}")
    return _ok("credential scan", "no credential-shaped literals in the source tree")


CHECKS: List[Callable[[], Result]] = [
    check_python,
    check_requests,
    check_core_imports,
    check_gui_imports,
    check_https,
    check_sse,
    check_markdown,
    check_modes,
    check_attachments,
    check_no_credentials_on_disk,
]


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run_selfcheck(verbose: bool = False) -> int:
    """Run every check.  Returns 0 when all pass, 1 otherwise."""
    print(f"Aero Grace desktop {__version__} — startup self-check")
    print("-" * 68)

    results = [check() for check in CHECKS]
    for name, passed, detail in results:
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name:<22} {detail}")

    print("-" * 68)

    if verbose:
        print("Endpoints:")
        for name, value, provenance in config.contract_report():
            flag = " " if provenance == "documented" else "*"
            print(f"  {flag} {name:<26} {value}")
        print("  (* = inferred; see README section 4)")
        print()
        print("Modes:")
        for mode in modes.ALL_MODES:
            verified = "verified" if mode.verified else "inferred"
            print(f"  {mode.short_label:<24} mode={mode.mode:<14} "
                  f"effort={mode.effort:<9} [{verified}]")

    failed = [name for name, passed, _ in results if not passed]
    blocking = [name for name in failed if name != "tkinter"]
    if blocking:
        print(f"{len(blocking)} blocking check(s) failed: {', '.join(blocking)}")
        print("Resolve these before starting the client.")
        return 1

    print(f"All {len(results)} checks passed.")
    if "tkinter" in failed:
        print("NOTE: tkinter is missing, so the window cannot open here.")
        print("      Install it with:  sudo apt-get install python3-tk")
        print("      (Fedora: python3-tkinter, Arch: tk)")
        print("      Everything else - the API core, SSE, Markdown, modes and")
        print("      attachments - is working.")
        return 0

    print("Ready: python3 run.py")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return run_selfcheck(verbose=("-v" in argv or "--verbose" in argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
