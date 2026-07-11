"""Tool package — each submodule self-registers via `@tool(...)`.

Importing this package imports every tool module, triggering decorator-based
registration into the shared registry in `_registry.py`. The server calls
`build_registry()` to get the active tool set.
"""

from __future__ import annotations

from ._registry import ToolSpec, all_tools, build_registry, tool

# Import side effects register each module's tools. Keep these imports even though
# they look unused — removing one unregisters its tools.
from . import status_tools  # noqa: F401
from . import transcribe_tools  # noqa: F401

ALL_TOOLS = all_tools()

__all__ = ["ToolSpec", "all_tools", "build_registry", "tool", "ALL_TOOLS"]
