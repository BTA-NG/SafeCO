"""Compatibility wrapper for the SafeCO FastAPI application.

The canonical app entry point is ``safeco.app``. This module remains as a thin
backwards-compatible import path for older callers.
"""

from __future__ import annotations

from safeco.app import app

__all__ = ["app"]
