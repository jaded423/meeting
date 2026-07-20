"""Stdio MCP server for meeting.

Registers every tool in the package (no feature flags — meeting has no OAuth
scopes to gate on). Logs go to stderr; stdout is reserved for MCP protocol frames.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    Tool,
)

from . import __version__
from .settings import load_settings
from .tools import ToolSpec, build_registry


def _meeting_prompt_text(input_value: str) -> str:
    """The /meeting workflow: transcribe → extract action items → route via gsuite.

    Reads settings at prompt-fetch time so the approval-gate wording reflects the
    user's current config.
    """
    cfg = load_settings()
    inp = input_value or "<the audio file, URL, or text file the user named>"
    if cfg.approval_gate:
        gate = (
            "BEFORE creating anything, list every proposed calendar event and task "
            "(with owner, date/time, and source quote) and ask the user to approve. "
            "Only call the gsuite tools after they confirm."
        )
    else:
        gate = (
            "Create the events and tasks directly (approval_gate is off), then report "
            "what you made."
        )
    return f"""You are running the /meeting workflow. Input: {inp}

1. Call `meeting_transcribe` with input="{inp}". It accepts an audio/video file, a
   URL (YouTube / Loom / Fathom share), or an already-transcribed text file. If it
   returns ok:false, stop and report the error (try `meeting_status` to diagnose).
2. Read the transcript. Extract the AGREED action items and any dated commitments.
   For each: the owner, the action, and a date/time if one was stated or clearly implied.
3. Route each item using the gsuite MCP tools:
   - Has a specific date/time (a meeting, a dated deadline) → `calendar_create_event`.
   - Actionable but undated ("Cody to review the deck") → `tasks_create` (a Google Task
     that Erica/Cody will date later — Tasks render in Cody's Calendar sidebar).
4. {gate}
5. Summarize what you created (events + tasks) with links.

Keep names accurate (Cody, Justin, Erica, Cynthia, Joe, Elevated Trading). Use the
user's own Google account (their gsuite instance) for all writes."""


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


log = logging.getLogger("meeting.server")


def _build_server() -> tuple[Server, dict[str, ToolSpec]]:
    registry = build_registry()
    log.info("meeting %s starting; tools=%s", __version__, sorted(registry))

    server: Server = Server("meeting")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
            )
            for spec in registry.values()
        ]

    @server.list_prompts()
    async def _list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="meeting",
                description=(
                    "Turn a meeting recording into calendar events + tasks: transcribe the "
                    "audio/URL/text, extract agreed action items, and route them to Google "
                    "Calendar (dated) or Google Tasks (undated) via gsuite."
                ),
                arguments=[
                    PromptArgument(
                        name="input",
                        description="Audio/video file path, a URL, or a text-transcript file.",
                        required=True,
                    )
                ],
            )
        ]

    @server.get_prompt()
    async def _get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        if name != "meeting":
            raise ValueError(f"unknown prompt: {name}")
        input_value = (arguments or {}).get("input", "")
        return GetPromptResult(
            description="Meeting → calendar/tasks workflow",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=_meeting_prompt_text(input_value)),
                )
            ],
        )

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        spec = registry.get(name)
        if spec is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"ok": False, "error": f"unknown tool: {name}", "retryable": False}
                    ),
                )
            ]
        args = arguments or {}
        try:
            # Handlers are sync and long-running (a transcription subprocess).
            # Offload to a thread so we don't stall the MCP event loop.
            result = await asyncio.to_thread(spec.handler, **args)
        except TypeError as exc:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"ok": False, "error": f"bad arguments for {name}: {exc}", "retryable": False}
                    ),
                )
            ]
        except Exception as exc:  # noqa: BLE001 — surface every failure as a structured error
            log.exception("tool %s failed", name)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"ok": False, "error": f"{type(exc).__name__}: {exc}", "retryable": True}
                    ),
                )
            ]
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return server, registry


async def _run() -> None:
    _setup_logging()
    server, _ = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
