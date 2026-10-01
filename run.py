#!/usr/bin/env python3
"""Run the Aero Grace desktop client.

    python run.py            # normal start
    python run.py --debug    # verbose (redacted) logging on stderr

Requirements: Python 3.9+, ``requests``, and a Tk-capable Python build
(``python3-tk`` on Debian/Ubuntu).
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main() -> int:
    from grace.ui.app import main as app_main

    return app_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
