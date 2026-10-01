"""Aero Grace desktop client.

A production-quality desktop client for Aero's Grace AI assistant.

The package is split into two layers:

``grace`` (no GUI imports)
    Configuration, API client, SSE parsing, conversation/session state,
    attachment handling, mode registry and error taxonomy.  Everything in
    this layer is pure Python and is unit tested without a display.

``grace.ui``
    Tkinter rendering layer.  Thin: it subscribes to events emitted by
    :class:`grace.controller.GraceController` and paints them.
"""

from __future__ import annotations

__version__ = "1.0.0"
APP_NAME = "Aero Grace"
APP_ID = "aero-grace-desktop"

__all__ = ["__version__", "APP_NAME", "APP_ID"]
