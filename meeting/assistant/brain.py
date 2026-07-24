"""Headless-Claude brain: transcript → Calendar/Tasks, via `claude -p`.

Same move as the `todo()` shell wrapper: `ANTHROPIC_API_KEY=` forces
subscription auth (uses the Max plan — no API key, no metered cost), and
`claude -p` runs headless. The app holds no meeting intelligence beyond this
prompt; it transcribes and relays.

Two modes:
  - propose (default): grant NO write tools, just list what it WOULD create.
    Safe to run anywhere; this is the approval gate.
  - route (--route):   grant the gsuite Calendar/Tasks tools so it actually
    creates the events/tasks. Requires the gsuite MCP to be registered with the
    `claude` CLI (user scope), not just Claude Desktop.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from typing import Any, NamedTuple

_PROMPT = """You are the Meeting Assistant router. Below is a meeting transcript{diar}.

Extract ONLY the agreed action items and dated commitments — not every topic
discussed. For each item identify:
  - owner: who is responsible (use the speaker labels / names in the transcript)
  - action: a concise imperative
  - when: a date/time if one was stated or clearly implied, else none

{mode}

TRANSCRIPT:
---
{transcript}
---
"""

_PROPOSE = (
    "DO NOT create anything or call any tools. Output a numbered list, one line "
    "each: `[owner] action — <date or 'no date'>  (Calendar event | Task)`. "
    "Mark items with a specific date/time as Calendar events, undated ones as "
    "Tasks. End with a one-line note of anything ambiguous a human should confirm."
)

_ROUTE = (
    "For each item: if it has a specific date/time, create a Google Calendar "
    "event with `calendar_create_event`; otherwise create a Task with "
    "`tasks_create`. Use the primary calendar / default task list. After "
    "creating them, output a numbered summary of exactly what you created "
    "(title + date + which owner), so the human can verify."
)


class BrainResult(NamedTuple):
    ok: bool
    output: str
    error: str
    seconds: float


def route(
    transcript: str,
    *,
    account: str = "elevated",
    diarized: bool = False,
    do_route: bool = False,
    timeout: int = 900,
) -> BrainResult:
    import time

    mode = _ROUTE if do_route else _PROPOSE
    prompt = _PROMPT.format(
        diar=" (with speaker labels)" if diarized else "",
        mode=mode,
        transcript=transcript,
    )

    cmd = ["claude", "-p", "--dangerously-skip-permissions"]
    if do_route:
        prefix = f"mcp__gsuite-{account}__"
        cmd += [
            "--allowedTools",
            f"{prefix}calendar_create_event",
            f"{prefix}calendar_list_calendars",
            f"{prefix}tasks_create",
            f"{prefix}tasklists_list",
        ]
    else:
        # propose-only: forbid anything that could write.
        cmd += ["--disallowedTools", "Bash", "Task", "Agent"]

    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = ""  # force subscription auth (no API cost)

    started = time.time()
    try:
        # Prompt goes on stdin (transcripts can exceed ARG_MAX).
        proc = subprocess.run(
            cmd, input=prompt, env=env,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return BrainResult(False, "", f"claude -p timed out after {timeout}s",
                          time.time() - started)
    except OSError as exc:
        return BrainResult(False, "", f"failed to launch claude: {exc}",
                          time.time() - started)

    return BrainResult(
        ok=proc.returncode == 0,
        output=(proc.stdout or "").strip(),
        error=(proc.stderr or "").strip(),
        seconds=time.time() - started,
    )


# ── Structured path (the GUI approve panel) ─────────────────────────────────
#
# The CLI's `route()` deals in free text. The app needs *structured* items so it
# can render editable rows + invite chips, let the human fix them, then create
# exactly the approved set. Two calls:
#   propose_structured() → claude reads the transcript, returns a JSON array.
#   create_items()       → claude creates the approved rows via the gsuite tools.

_PROPOSE_JSON = """You are the Meeting Assistant. Below is a meeting transcript{diar}.

This meeting took place on {anchor}. The person running this app is {me_name}.
{roster}
Extract ONLY the agreed action items and dated commitments — not every topic discussed.

Output ONLY a JSON array and nothing else — no prose, no markdown code fences. Each element:
{{
  "owner": "<full name of who is responsible, or \\"unassigned\\">",
  "action": "<concise imperative>",
  "date": "<YYYY-MM-DD, or \\"YYYY-MM-DD HH:MM\\" if a time was stated, or null>",
  "type": "event" or "task",
  "participants": ["<full names of people OTHER than {me_name} to loop in>"],
  "ambiguous": "<one short note if a human should confirm something, else null>"
}}

Rules:
- Resolve EVERY relative date ("Friday", "next Monday", "in 3 days", "tomorrow") against the
  MEETING date {anchor} — NOT the current date. "this Friday" means the Friday after {anchor}.
- "type" is "event" if the item has a date OR involves someone other than {me_name}; otherwise "task".
- "participants" = the owner (when not {me_name}) plus anyone else named responsible. Never list {me_name}.
- Prefer full names exactly as they appear in the known-people list when you can.

TRANSCRIPT:
---
{transcript}
---
"""

_CREATE_JSON = """Create the following calendar events and Google Tasks EXACTLY as specified,
using the gsuite tools. Do NOT add, drop, merge, or reinterpret any item — create each one as given.

For each item:
- "event": call calendar_create_event on the primary calendar. summary = action.
  If it has a date+time, make a 30-minute event; if a date only, make it an all-day event.
  If "invitees" is non-empty, pass attendees=<those emails> and send_updates="all".
- "task": call tasks_create on the default task list. title = action; set the due date if present.

After creating them all, output a numbered summary — one line each: title · date · Event/Task · guests.

ITEMS (JSON):
{items}
"""


def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """Pull a JSON array out of claude's stdout (tolerant of ``` fences / stray prose)."""
    if not text:
        return None
    i, j = text.find("["), text.rfind("]")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        data = json.loads(text[i : j + 1])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def propose_structured(
    transcript: str,
    *,
    diarized: bool = False,
    me_name: str = "the user",
    roster_names: list[str] | None = None,
    anchor_date: str | None = None,
    timeout: int = 900,
) -> tuple[list[dict[str, Any]], BrainResult]:
    """Ask the brain for a JSON list of action items. Returns (items, raw_result).

    `anchor_date` (YYYY-MM-DD) is the MEETING date that relative dates resolve
    against — pass the real meeting date so "this Friday" in an old recording maps
    to the Friday after the meeting, not after today. Defaults to today's date.

    `items` is [] if claude produced no parseable array (check `result.ok`/`.error`).
    No write tools are granted — this is the read-only propose stage.
    """
    import time

    anchor = anchor_date or datetime.date.today().isoformat()
    roster = ""
    if roster_names:
        roster = "Known people: " + ", ".join(roster_names) + ".\n"
    prompt = _PROPOSE_JSON.format(
        diar=" (with speaker labels)" if diarized else "",
        anchor=anchor,
        me_name=me_name,
        roster=roster,
        transcript=transcript,
    )

    cmd = [
        "claude", "-p", "--dangerously-skip-permissions",
        "--disallowedTools", "Bash", "Task", "Agent",
    ]
    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = ""  # subscription auth, no API cost

    started = time.time()
    try:
        proc = subprocess.run(
            cmd, input=prompt, env=env,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [], BrainResult(False, "", f"claude -p timed out after {timeout}s", time.time() - started)
    except OSError as exc:
        return [], BrainResult(False, "", f"failed to launch claude: {exc}", time.time() - started)

    out = (proc.stdout or "").strip()
    res = BrainResult(
        ok=proc.returncode == 0,
        output=out,
        error=(proc.stderr or "").strip(),
        seconds=time.time() - started,
    )
    items = _extract_json_array(out) or []
    return items, res


def create_items(
    items: list[dict[str, Any]],
    *,
    account: str = "elevated",
    timeout: int = 900,
) -> BrainResult:
    """Create the approved items via gsuite. Each item: {action, date, type, invitees:[emails]}."""
    import time

    payload = [
        {
            "action": it.get("action", ""),
            "date": it.get("date"),
            "type": it.get("type", "task"),
            "invitees": [e for e in (it.get("invitees") or []) if e],
        }
        for it in items
    ]
    prompt = _CREATE_JSON.format(items=json.dumps(payload, indent=2))

    prefix = f"mcp__gsuite-{account}__"
    cmd = [
        "claude", "-p", "--dangerously-skip-permissions",
        "--allowedTools",
        f"{prefix}calendar_create_event",
        f"{prefix}calendar_list_calendars",
        f"{prefix}tasks_create",
        f"{prefix}tasklists_list",
    ]
    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = ""

    started = time.time()
    try:
        proc = subprocess.run(
            cmd, input=prompt, env=env,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return BrainResult(False, "", f"claude -p timed out after {timeout}s", time.time() - started)
    except OSError as exc:
        return BrainResult(False, "", f"failed to launch claude: {exc}", time.time() - started)

    return BrainResult(
        ok=proc.returncode == 0,
        output=(proc.stdout or "").strip(),
        error=(proc.stderr or "").strip(),
        seconds=time.time() - started,
    )
