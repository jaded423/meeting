"""Structured error helper for tool handlers.

Every tool failure returns a dict with `error` (message) and `retryable` (bool),
plus optional context. The server wraps *uncaught* exceptions in the same shape
(see server.py), so handler-level validation errors go through this helper.

`retryable=False` is right for input validation (the caller must fix something
first). Transient failures — a transcription subprocess that timed out or died —
are `retryable=True`.
"""

from __future__ import annotations

from typing import Any


def error(message: str, *, retryable: bool = False, **extra: Any) -> dict[str, Any]:
    """Build a structured error dict. Extra kwargs are merged into the payload."""
    return {"ok": False, "error": message, "retryable": retryable, **extra}
