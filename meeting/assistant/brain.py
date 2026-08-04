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
import time
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


# ── account binding ─────────────────────────────────────────────────────────
#
# Every brain call runs with `--dangerously-skip-permissions`, which bypasses
# ALL permission checks — so `--allowedTools mcp__gsuite-elevated__…` never bound
# anything. It is a permission allowlist, and there were no permissions to grant.
# With four `gsuite-*` servers in the user's global config, the model saw four
# identical `calendar_create_event` tools and was free to pick any of them.
#
# Found live 2026-07-27: a run with account="elevated" mailed the transcript from
# joshua@elevatedtrading.com (right account) and created the events on
# jaded423@gmail.com (wrong account) — a Point4 meeting landed on a personal
# calendar, next to family birthdays. Different tool call, different account,
# same run. Nothing in the logs said so; it looked like a success.
#
# Binding must be structural, not advisory: hand `claude` a config containing
# ONLY the selected account's server plus `--strict-mcp-config`, so the other
# accounts do not exist in that session and cannot be chosen by accident.

_CLAUDE_CONFIG = os.path.expanduser("~/.claude.json")


class AccountBindingError(RuntimeError):
    """The selected account's MCP server could not be pinned down."""


def _account_mcp_config(account: str) -> str:
    """Write a one-server MCP config for `account`; return its path.

    Raises `AccountBindingError` rather than falling back to the global config —
    a run that cannot prove which Google account it will write to must not run.
    """
    name = f"gsuite-{account}"
    try:
        with open(_CLAUDE_CONFIG, encoding="utf-8") as fh:
            servers = (json.load(fh) or {}).get("mcpServers") or {}
    except (OSError, json.JSONDecodeError) as exc:
        raise AccountBindingError(
            f"could not read {_CLAUDE_CONFIG} to find the '{name}' server: {exc}"
        ) from None
    entry = servers.get(name)
    if not entry:
        known = ", ".join(sorted(k for k in servers if k.startswith("gsuite-"))) or "none"
        raise AccountBindingError(
            f"no MCP server named '{name}' is registered (found: {known}). Refusing to "
            "run, because there would be no way to guarantee which Google account "
            "gets written to."
        )
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = os.path.join(CONFIG_DIR, f"mcp-{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"mcpServers": {name: entry}}, fh, indent=2)
    return path


def _bind(cmd: list[str], account: str) -> list[str]:
    """Append the flags that pin this invocation to one Google account."""
    return cmd + ["--mcp-config", _account_mcp_config(account), "--strict-mcp-config"]


def _run(cmd: list[str], prompt: str, timeout: int) -> BrainResult:
    """Run one `claude -p` call with the prompt on stdin. Never raises.

    stdin rather than argv because transcripts blow past ARG_MAX, and
    ``ANTHROPIC_API_KEY=""`` forces subscription auth so no call here is metered.
    """
    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = ""

    started = time.time()
    try:
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


def route(
    transcript: str,
    *,
    account: str = "elevated",
    diarized: bool = False,
    do_route: bool = False,
    timeout: int = 900,
) -> BrainResult:
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
        try:
            cmd = _bind(cmd, account)   # the flags above document intent; this enforces it
        except AccountBindingError as exc:
            return BrainResult(ok=False, output="", error=str(exc), seconds=0.0)
    else:
        # propose-only: forbid anything that could write.
        cmd += ["--disallowedTools", "Bash", "Task", "Agent"]

    return _run(cmd, prompt, timeout)


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
- "type" is "event" whenever you have — or can derive — a date, EVEN IF no time was stated.
  Default to "event". Only an event can carry the other people as guests and actually notify
  them; a task cannot, so anything involving someone else belongs on the calendar.
- "type" is "task" ONLY when there is no date at all. Google Calendar cannot create a dateless
  event. Still list the people in "participants", and say so in "ambiguous" (e.g. "needs a
  date to invite Cody") so a human can supply one and it becomes an event.
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
  Pass "date" through as `start` UNCHANGED. The tool reads both `YYYY-MM-DD` (all-day) and
  `YYYY-MM-DD HH:MM` (timed) — so do NOT reformat it, do NOT add a timezone, and do NOT
  compute an `end`. Omit `end` and let the tool default (one day, or 30 minutes).
  If "guest_emails" is non-empty, pass attendees=<those emails>. Do NOT pass send_updates —
  the tool emails attendees by default.
- "task": call tasks_create on the default task list. title = action, `due` = "date" if present.
  If "notes" is non-empty pass it as `notes` (Tasks has no guest list, so that is where the
  people involved are recorded).

When every item is done, output ONLY a JSON array and nothing else — no prose, no markdown
fences, no commentary — with one element per item, in the SAME ORDER you were given:
{{
  "action": "<the action you were given, unchanged>",
  "type": "event" or "task",
  "date": "<the date you were given, or null>",
  "guests": ["<address you actually attached>"],
  "ok": true or false,
  "link": "<htmlLink the tool returned, else null>",
  "error": "<one short line if it failed, else null>"
}}

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
    res = _run(cmd, prompt, timeout)
    return _extract_json_array(res.output) or [], res


def create_items(
    items: list[dict[str, Any]],
    *,
    account: str = "elevated",
    timeout: int = 900,
) -> tuple[list[dict[str, Any]], BrainResult]:
    """Create the approved items via gsuite. Returns (results, raw_result).

    Each input item: {action, date, type, invitees:[emails], notes}. Each result:
    {action, type, date, guests, ok, link, error} — structured on purpose. The
    router's own prose used to be pasted into the audit email verbatim, which
    mailed the reader file paths, API errors and offers to patch code; it reads
    as an internal dev log to anyone who isn't the developer. The prose stays in
    `raw_result.output` for the log; only this survives into the email.

    `results` is [] if the router produced no parseable array — the items may
    still have been created, so treat it as "unknown", not "nothing happened".
    """
    payload = [
        {
            "action": it.get("action", ""),
            "date": it.get("date"),
            "type": it.get("type", "task"),
            "guest_emails": [e for e in (it.get("invitees") or []) if e],
            "notes": it.get("notes") or "",
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
    try:
        cmd = _bind(cmd, account)   # the flags above document intent; this enforces it
    except AccountBindingError as exc:
        return [], BrainResult(ok=False, output="", error=str(exc), seconds=0.0)
    res = _run(cmd, prompt, timeout)
    return _extract_json_array(res.output) or [], res


# ── Claude sign-in (subscription auth) ──────────────────────────────────────
#
# The brain runs on the user's Claude subscription, not an API key — `_run()`
# blanks ANTHROPIC_API_KEY so it always resolves that way. That sign-in expires
# periodically, and when it does every brain call fails with a stderr blob no
# non-technical user will connect to "log in again". So: check before doing any
# work, and hand back a fix-it action instead of an error.

CONFIG_DIR = os.path.expanduser("~/.config/meeting-assistant")
AUTH_COMMAND = os.path.join(CONFIG_DIR, "auth.command")

_AUTH_SCRIPT = """#!/bin/sh
# Meeting Assistant — sign in to Claude.
# Double-click this file. It opens a Terminal window and signs you in.
# Generated by the Meeting Assistant; safe to delete (it will be recreated).

printf '\\n  Meeting Assistant — Claude sign-in\\n'
printf '  ─────────────────────────────────────────\\n\\n'

# A double-clicked .command may not inherit the PATH from your shell profile.
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/bin"; do
  case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH
unset ANTHROPIC_API_KEY   # force subscription sign-in, never an API key

if ! command -v claude >/dev/null 2>&1; then
  printf '  Claude Code is not installed on this Mac.\\n\\n'
  printf '  Install it first:\\n'
  printf '    npm install -g @anthropic-ai/claude-code\\n\\n'
  printf '  Then double-click this file again.\\n\\n'
  printf '  Press Return to close.'; read _ ; exit 1
fi

printf '  A browser window will open. Sign in with your Claude account\\n'
printf '  (the same one you use at claude.ai), then come back here.\\n\\n'

claude auth login

printf '\\n'
if claude auth status --json 2>/dev/null | grep -q '"loggedIn": *true'; then
  printf '  ✓ Signed in. You can close this window and use the app.\\n\\n'
else
  printf '  ✗ Still not signed in. Try again, or send this window to Joshua.\\n\\n'
fi
printf '  Press Return to close.'; read _
"""


class AuthStatus(NamedTuple):
    ok: bool          # signed in and ready
    installed: bool   # the `claude` CLI exists at all
    detail: str       # human-readable reason when not ok


def ensure_auth_command() -> str:
    """Write (or refresh) the double-clickable sign-in helper; return its path.

    Generated rather than shipped so there's one source of truth and no
    packaging path to get wrong — it's always present and always current.
    """
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        current = ""
        if os.path.isfile(AUTH_COMMAND):
            with open(AUTH_COMMAND, encoding="utf-8") as fh:
                current = fh.read()
        if current != _AUTH_SCRIPT:
            with open(AUTH_COMMAND, "w", encoding="utf-8") as fh:
                fh.write(_AUTH_SCRIPT)
        os.chmod(AUTH_COMMAND, 0o755)
    except OSError:
        pass  # non-fatal: the UI still tells them the command to run by hand
    return AUTH_COMMAND


def auth_status(timeout: int = 30) -> AuthStatus:
    """Is the Claude CLI installed and signed in? Never raises."""
    try:
        proc = subprocess.run(
            ["claude", "auth", "status", "--json"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return AuthStatus(False, False, "Claude Code isn't installed on this Mac.")
    except (OSError, subprocess.SubprocessError) as exc:
        return AuthStatus(False, True, f"Couldn't check the Claude sign-in: {exc}")

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        # unparseable output — treat as usable rather than blocking a good run
        return AuthStatus(proc.returncode == 0, True, (proc.stderr or "").strip())

    if data.get("loggedIn"):
        return AuthStatus(True, True, str(data.get("authMethod") or ""))
    return AuthStatus(False, True, "You're not signed in to Claude.")


_AUTH_SIGNS = (
    "not logged in", "please log in", "log in to", "authentication",
    "unauthorized", "401", "invalid api key", "oauth", "auth token",
    "session expired", "credit balance",
)


def looks_like_auth_failure(result: BrainResult) -> bool:
    """Backstop for a sign-in that expires mid-run, after the pre-flight passed."""
    blob = f"{result.error}\n{result.output}".lower()
    return any(s in blob for s in _AUTH_SIGNS)


# ── Completeness safety net ─────────────────────────────────────────────────
#
# The failure mode this exists for: for a meeting you did NOT attend, you have no
# ground truth, so an item the first pass silently dropped is invisible. Three
# independent nets, because each catches a different miss:
#   audit_coverage()   — a second, adversarial read that assumes something WAS missed
#   the topic ledger   — makes coverage visible ("7 topics → 5 items") instead of implied
#   email_transcript() — the raw source, recoverable even when both passes are wrong

_AUDIT_JSON = """You are the Meeting Assistant's completeness checker — a SECOND pass over a
meeting transcript{diar} that a first pass has already read.

The first pass produced the items under FIRST PASS below. It is known to UNDER-include: it
drops commitments made in passing, and commitments owned by someone other than {me_name}.
Your job is to find what it missed. Assume it missed something until the transcript shows
otherwise.

This meeting took place on {anchor}. The person running this app is {me_name}.
{roster}
Work in two steps.

STEP 1 — Topics. List every distinct topic or thread that got real airtime (a subject that was
actually discussed, not every sentence). Give each a status:
  - "covered"   — it produced a commitment that IS already in FIRST PASS
  - "no-action" — genuinely discussion only; nobody agreed to do anything
  - "missed"    — somebody agreed to do something (build / send / check / write / decide /
                  follow up / get back to someone) and it is NOT in FIRST PASS
When torn between "no-action" and "missed", choose "missed". A human reviews every candidate
before anything is created, so a false alarm costs one glance — a real miss costs a dropped
deliverable.

STEP 2 — Missed items. For each topic you marked "missed", write the action item the first
pass should have produced.

Output ONLY a JSON object and nothing else — no prose, no markdown code fences:
{{
  "topics": [
    {{"topic": "<short label, 8 words max>",
      "status": "covered" | "no-action" | "missed",
      "note": "<12 words max: what was agreed, or why nothing was>"}}
  ],
  "missed": [
    {{"owner": "<full name of who is responsible, or \\"unassigned\\">",
      "action": "<concise imperative>",
      "date": "<YYYY-MM-DD, or \\"YYYY-MM-DD HH:MM\\" if a time was stated, or null>",
      "type": "event" or "task",
      "participants": ["<full names of people OTHER than {me_name} to loop in>"],
      "ambiguous": "<one short note if a human should confirm something, else null>"}}
  ]
}}

Rules:
- Resolve EVERY relative date ("Friday", "next Monday", "tomorrow") against the MEETING date
  {anchor} — NOT the current date.
- "type" is "event" whenever you have or can derive a date, even with no stated time — default
  to "event", since only an event carries guests and notifies them. "task" ONLY when there is
  no date at all (Calendar cannot create a dateless event); then list the people in
  "participants" and note "needs a date to invite X" in "ambiguous".
- "missed" holds ONLY new items — never repeat something already in FIRST PASS.
- One "missed" entry per topic marked "missed". If a topic hid two commitments, split it into
  two topics.
- Prefer full names exactly as they appear in the known-people list when you can.

FIRST PASS (already captured):
{first_pass}

TRANSCRIPT:
---
{transcript}
---
"""

_STATUSES = ("covered", "no-action", "missed")


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of claude's stdout (tolerant of ``` fences / stray prose)."""
    if not text:
        return None
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        data = json.loads(text[i : j + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _first_pass_lines(items: list[dict[str, Any]]) -> str:
    if not items:
        return "(nothing — the first pass came back empty, so treat every commitment as missed)"
    return "\n".join(
        f"{n}. [{it.get('owner') or 'unassigned'}] {it.get('action', '')}"
        f" — {it.get('date') or 'no date'} ({it.get('type', 'task')})"
        for n, it in enumerate(items, 1)
    )


def _normalize_coverage(data: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce the audit JSON into a shape the UI can render without defensive checks."""
    topics: list[dict[str, str]] = []
    missed: list[dict[str, Any]] = []
    for t in (data or {}).get("topics") or []:
        if not isinstance(t, dict) or not str(t.get("topic", "")).strip():
            continue
        status = str(t.get("status", "")).strip().lower()
        topics.append({
            "topic": str(t["topic"]).strip(),
            # an unrecognised status is treated as "missed" — fail toward the human
            "status": status if status in _STATUSES else "missed",
            "note": str(t.get("note") or "").strip(),
        })
    for m in (data or {}).get("missed") or []:
        if isinstance(m, dict) and str(m.get("action", "")).strip():
            missed.append(m)
    return {"topics": topics, "missed": missed}


def audit_coverage(
    transcript: str,
    items: list[dict[str, Any]],
    *,
    diarized: bool = False,
    me_name: str = "the user",
    roster_names: list[str] | None = None,
    anchor_date: str | None = None,
    timeout: int = 900,
) -> tuple[dict[str, Any], BrainResult]:
    """Second-pass completeness check. Returns ({topics, missed}, raw_result).

    A fresh `claude -p` re-reads the transcript knowing what the first pass caught,
    and is prompted to assume something was dropped. Read-only: no write tools are
    granted, and every candidate it returns lands UNCHECKED in the review panel.

    On any failure this returns an empty ledger rather than raising — a broken audit
    must never block the items the first pass did find.
    """
    anchor = anchor_date or datetime.date.today().isoformat()
    roster = ""
    if roster_names:
        roster = "Known people: " + ", ".join(roster_names) + ".\n"
    prompt = _AUDIT_JSON.format(
        diar=" (with speaker labels)" if diarized else "",
        anchor=anchor,
        me_name=me_name,
        roster=roster,
        first_pass=_first_pass_lines(items),
        transcript=transcript,
    )

    cmd = [
        "claude", "-p", "--dangerously-skip-permissions",
        "--disallowedTools", "Bash", "Task", "Agent",
    ]
    res = _run(cmd, prompt, timeout)
    return _normalize_coverage(_extract_json_object(res.output)), res


_GLYPH = {"covered": "✓", "no-action": "·", "missed": "⚠"}


def format_created(results: list[dict[str, Any]] | None) -> str:
    """Render `create_items` results as the reader-facing CREATED section.

    One line per item — no router prose, no file paths, no stack traces. A
    failure is shown as a failure rather than dropped, because the whole point
    of the audit email is that it records what did NOT happen too.
    """
    if not results:
        return ("The router returned no itemised result for this run — check Calendar and "
                "Tasks directly to confirm what landed.")
    lines: list[str] = []
    for r in results:
        kind = "Event" if str(r.get("type", "")).lower() == "event" else "Task"
        when = str(r.get("date") or "no date")
        guests = [g for g in (r.get("guests") or []) if g]
        who = f" · invited {', '.join(guests)}" if guests else ""
        if r.get("ok"):
            lines.append(f"  ✓ {r.get('action', '(untitled)')}  ·  {when}  ·  {kind}{who}")
        else:
            why = str(r.get("error") or "no reason given").strip()
            lines.append(f"  ✗ NOT created — {r.get('action', '(untitled)')}  ·  {kind}  ·  {why}")
    failed = sum(1 for r in results if not r.get("ok"))
    if failed:
        lines += ["", f"  {failed} of {len(results)} did not get created — see the ✗ lines above."]
    return "\n".join(lines)


def format_coverage(
    coverage: dict[str, Any],
    items: list[dict[str, Any]] | None = None,
    *,
    created: str = "",
) -> str:
    """Plain-text audit report — the body of the transcript email."""
    lines: list[str] = []
    topics = coverage.get("topics") or []
    if topics:
        n_missed = sum(1 for t in topics if t["status"] == "missed")
        lines.append(f"COVERAGE — {len(topics)} topics discussed, {n_missed} flagged as missed")
        lines.append("")
        for t in topics:
            note = f" — {t['note']}" if t.get("note") else ""
            lines.append(f"  {_GLYPH.get(t['status'], '·')} {t['topic']}{note}")
        lines.append("")
    else:
        lines += ["COVERAGE — the second pass returned no topic ledger for this run.", ""]

    if items:
        lines.append(f"ITEMS PROPOSED ({len(items)})")
        lines.append("")
        lines.append(_first_pass_lines(items))
        lines.append("")
    if created:
        lines += ["CREATED IN CALENDAR / TASKS", "", created, ""]
    lines.append("Full transcript attached — this email is the audit backup, so the raw")
    lines.append("source stays recoverable even if both extraction passes were wrong.")
    return "\n".join(lines)


_EMAIL_PROMPT = """Send exactly ONE email using the gsuite Gmail tool, then stop.

Call gmail_send_message once with:
  to:          {to}
  subject:     {subject}
  attachments: ["{path}"]
  body:        the text between the BODY markers below, verbatim

Do NOT open, read, summarize or quote the attachment — pass the path through untouched.
Do not send anything else and do not create a draft. Output only the message id you get back.

--- BODY ---
{body}
--- END BODY ---
"""


def email_transcript(
    to: str,
    subject: str,
    body: str,
    attachment_path: str,
    *,
    account: str = "elevated",
    timeout: int = 300,
) -> BrainResult:
    """Email the transcript as a file ATTACHMENT, with the audit report as the body.

    The transcript is passed by path, never through the model's context — a 2-hour
    meeting would otherwise cost more to mail than to transcribe, and risks being
    silently truncated or paraphrased on the way out.
    """
    path = os.path.expanduser(attachment_path or "")
    if not path or not os.path.isfile(path):
        return BrainResult(False, "", f"no transcript file to attach at: {attachment_path}", 0.0)

    prompt = _EMAIL_PROMPT.format(to=to, subject=subject, path=path, body=body)
    prefix = f"mcp__gsuite-{account}__"
    cmd = [
        "claude", "-p", "--dangerously-skip-permissions",
        "--allowedTools", f"{prefix}gmail_send_message",
        # belt-and-braces: it has no reason to read the file it is attaching
        "--disallowedTools", "Bash", "Read", "Task", "Agent",
    ]
    try:
        cmd = _bind(cmd, account)   # send AS this account, not whichever it picks
    except AccountBindingError as exc:
        return BrainResult(False, "", str(exc), 0.0)
    return _run(cmd, prompt, timeout)
