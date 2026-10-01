"""``python -m grace`` entry point."""

from __future__ import annotations

import sys

from .selfcheck import main as check_main
from .ui.app import main as app_main


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv or "--selfcheck" in argv:
        return check_main(argv)
    return app_main(argv)


if __name__ == "__main__":
    sys.exit(main())
