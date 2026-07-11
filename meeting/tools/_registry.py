"""Tool registry — decorator-based self-registration.

Mirrors gsuite's `tools/_registry.py`, minus the feature-flag dimension: meeting
has no OAuth scopes to gate on, so every registered tool is always active. Each
tool module decorates its handler with `@tool(...)`; import side-effects populate
`_REGISTRY`. Handlers are called with `**arguments` from the MCP client, so their
Python signatures must match the declared `input_schema` property names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


_REGISTRY: list[ToolSpec] = []


def tool(
    *, name: str, description: str, input_schema: dict[str, Any]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a handler as an MCP tool. Returns the fn unchanged so it stays
    directly callable by Python (tests, internal callers)."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if any(t.name == name for t in _REGISTRY):
            raise ValueError(f"duplicate tool registration: {name}")
        _REGISTRY.append(
            ToolSpec(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=fn,
            )
        )
        return fn

    return decorate


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY)


def build_registry() -> dict[str, ToolSpec]:
    return {t.name: t for t in _REGISTRY}
