---
type: reference
title: Meeting Assistant — architecture pivot + current state
tags: [meeting, meeting-assistant, trans, whisper, claude-cli, gsuite, design, pivot]
related: [changelog, meeting-to-tasks-pipeline]
---

# Meeting Assistant — the pivot (2026-07-20)

## TL;DR

The meeting→tasks product **pivoted from an MCP-inside-Claude-Desktop to a standalone
local app + a headless-`claude` brain.** The `meeting` MCP was a thin connector; a real
fresh-VM Desktop test exposed two fatal holes that the app design fixes. Core app is
**built and proven end-to-end on the dev machine tonight**; packaging + a native GUI
wrapper are the remaining work.

## What broke (the VM test that forced the pivot)

Cody's-settings VM test of `meeting-kit` surfaced two holes in the MCP-in-Desktop model:

1. **Long transcription blocks Claude Desktop.** The `meeting_transcribe` MCP call is
   synchronous; Desktop times out after a few minutes. A real 30–60 min meeting can never
   finish inside that window (first run also pays a one-time Whisper model download).
   Observed: ~4-min throbber then "Local trans stack didn't respond," and separately a
   35-min transcript that hit a **Whisper hallucination loop** ("Okay. Okay. Okay." on
   silence).
2. **No "who said what" → can't route per person.** Without speaker labels you can't
   attribute an action item to an owner, so you can't know whose Calendar to add to.

Root cause: the MCP put the **slow, heavy, deterministic** part (download + transcribe)
*inside* the **smart, interactive** part (Claude Desktop). Opposite needs.

## The new architecture

Split them. Muscle in a local app, brain in a headless `claude` call — the same two
patterns Joshua already ships: **photoEditor** (local batch media processing) +
**`todo()`** (a dumb shell relay to `claude -p`).

| Piece | Where it lives | Notes |
|---|---|---|
| Transcription (heavy) | **the app** (`meeting/assistant/transcribe.py`) | drives `mlx_whisper` directly → live progress bar + ETA; anti-hallucination flags. Not time-boxed → can afford `transd` diarization for speaker labels. |
| Relay to the brain | **the app** (`brain.py`) | `ANTHROPIC_API_KEY= claude -p …` — subscription auth, **no API key/cost**. Same move as `todo()`. |
| *What to do* with the transcript | **the prompt in `brain.py`** (baked in for self-contained distribution) | extract agreed action items → owner/date → Calendar-vs-Task classification |
| Calendar/Tasks hands | **gsuite MCP** (attached to the `claude` CLI) | the ONLY MCP still in the loop |

**No monthly sub:** local Whisper is free; the brain runs on the Max plan both Joshua and
Cody already have (headless `claude -p`, blanked `ANTHROPIC_API_KEY`). No new subscription,
no metered API.

**The `meeting` MCP is demoted.** Nothing in the new flow calls `meeting_transcribe` /
`meeting_status` / the `/meeting` prompt — transcription is the app's job (via
`trans_runner` directly), routing is gsuite's. The MCP isn't deleted (could stay as an
optional "transcribe from a chat" convenience) but it is **off the critical path.** Its one
surviving organ is `trans_runner.py`, reused by the app.

## What's built + PROVEN (dev machine, 2026-07-20)

New package `meeting/assistant/`: `transcribe.py` (progress + ETA + anti-hallucination),
`brain.py` (headless `claude -p`, propose/route modes), `cli.py` (orchestrator +
dependency-free progress bar), `__main__.py`. Console script `meeting-assistant` (added to
`pyproject.toml`).

Verified working end-to-end:
- text passthrough (instant), and a real audio clip: 16s → clean transcript in 3s, names/
  dates correct (vocab bias live), **no hallucination loop**.
- Live **progress bar + %/ETA** off `mlx_whisper` segment timestamps.
- **Brain (real `claude -p`, sub auth):** extracted 4 action items with owner + date +
  Calendar-vs-Task, and flagged ambiguities ("Monday 10am — today or next?"; unassigned
  item). ~14s.
- **Propose mode** (default, no writes) + **`--route`** wired (`gsuite-elevated` is ✔
  connected to the `claude` CLI, so route can actually create events/tasks).

Usage: `meeting-assistant <file|url|text> [--diarize] [--model large-v3] [--account elevated] [--route] [--skip-brain]`.
Default is safe (transcribe → propose, no writes). `--route` is the only thing that writes.

## GUI + routing design — SETTLED 2026-07-21 (spec for the build)

Design session before building the native app. Two things locked: how owner→invite routing
works, and the GUI architecture. A base **UI mockup** was built and approved →
artifact `https://claude.ai/code/artifact/5adf0c72-142e-41b5-b51e-acdcb2856f14` (setup /
progress / review-approve screens).

### Owner ≠ invite — the routing model

**Everything writes to ONE account: the person running the app.** Nobody has anyone else's
login, so we never write to another account. People other than the runner are looped in as
**calendar guests** — Google's invite system puts the event on their calendar with no login
of theirs required.

- Verified: `gsuite calendar_create_event` takes `attendees` (list of email strings) +
  `send_updates='all'` to actually email the invite (`gsuite/tools/calendar_tools.py`).
- **Asymmetry that shapes the classifier:** Google **Tasks can't have guests** (no assignee,
  no sharing). So *any item involving another person must be a Calendar event*, even an
  undated to-do (undated → all-day event). Only **your-own + undated** items stay Tasks.
- **Routing rule:** involves only you + undated → your **Task**; involves only you + dated →
  your **Event**; involves someone else → **Event on your calendar with them invited.**
- **name→email map** (new ingredient): the transcript says "Erica"; the invite needs her
  address. Seed from the Elevated team roster (Cody, Justin, Joe, Cynthia, Erica, Joshua),
  editable in-app. No email on file → fall back to name-in-title, no invite.
- The brain must separate **who's speaking** from **who owns the action** ("*Erica needs
  to…*" → invite Erica; "*I'll handle…*" → your own, no guest). Speaker labels + phrasing
  ("X needs to / X will") drive it — another concrete reason the `--diarize` toggle earns
  its keep.

### GUI architecture — thin front-end over the existing organs

No refactor: the GUI just drives the two pure functions already built —
`transcribe.transcribe(..., on_progress=cb)` and `brain.route(...)`. The `on_progress(done,
elapsed, total)` callback is already exactly what a progress bar consumes.

- **Thread pattern (lifted wholesale from photoEditor `tk_app/app.py`):** worker
  `threading.Thread` runs transcribe→brain; pushes progress into a `queue.Queue`;
  `root.after(200, poll)` drains it and touches Tk **only on the main thread**;
  `threading.Event` = cooperative Cancel. Never touch Tk from the worker.
- **Layout:** new `meeting/assistant/gui/` → `app.py` (window), `worker.py` (thread+queue),
  `__main__.py`. Muscle (`transcribe.py`/`brain.py`/`cli.py`) unchanged.
- **Packaging:** copy photoEditor's `build_app.sh` + `.spec` + `.icns`. Must build under a
  **python.org framework Python with working Tk**; carry over the `sys.frozen`/`sys._MEIPASS`
  resource-path idiom (whisper model, `vocab.txt`) and `setup_logging()` → `~/Library/Logs/`
  (a `--windowed` .app has no console — that's the only debug channel).

### v1 scope

Quality segmented control **Fast (small) / Balanced (medium) / Best (large-v3)** with live
ETA on each (audio-duration × per-model realtime factor); **speaker-labels** toggle;
**account** dropdown; **two-stage editable approve panel** (propose → editable rows with
owner/action/date/Event-vs-Task/**invite chips** → "Create N items"); **done notification**
(the walk-away payoff); **Cancel**. Deferred to v2: run history, editable vocab field,
dock-drop droplet mode.

## GUI BUILT + hardened through testing (2026-07-23)

The app is built to the spec above and driven through real-file runs. `meeting/assistant/gui/`
(`app.py`, `worker.py`, `contacts_dialog.py`) is a thin Tk front-end; `contacts.py` resolves
invite emails; `brain.propose_structured()`/`create_items()` give the editable review rows.
Both the fast-Whisper and diarized paths reach the review→create flow. Run:
`python -m meeting.assistant.gui` (or double-click the gitignored dev `MeetingAssistant.app`).

**Gotchas learned in testing (don't re-discover):**
- **MLX is arm64-only.** If the app runs under x86_64/Rosetta (a Rosetta terminal, or an app
  bundle launched x86_64), `mlx_whisper` dies with `incompatible architecture … need 'x86_64'`
  (exit 1). Fix in place: `trans_runner._arm64_prefix()` forces `arch -arm64` on the
  mlx_whisper/transd subprocess; the dev launcher forces arm64 too. The eventual PyInstaller
  `.app` must be built under **arm64 Python**.
- **mlx_whisper block-buffers piped stdout** → no live progress unless `PYTHONUNBUFFERED=1`.
- **pyannote diarization progress** — now real: `transd` prints `[diar] <step> c/t (p%)` under
  `TRANS_PROGRESS=1` (a custom hook on `pipeline(hook=…)`), parsed by `trans_runner` → a
  determinate bar + ETA through segmentation + embeddings. (pyannote's clustering/counting
  sub-steps are instant and report no progress, so they're omitted from the step count.)
- **Google Tasks can't carry guests** → any item involving another person is created as an
  Event so it can invite them (undated → all-day). Only your-own+undated stays a Task.

## What's left (see TODO.md)

- **Shakeout runs by Joshua** — confirm the review→`Create` flow lands events/tasks + invites
  on a live calendar; both paths; then a Cody-settings timed run on the VM.
- **Completeness safety net** — for meetings Joshua wasn't in, catch items the brain missed:
  email the diarized transcript to a configurable address (quick win) and/or a second-pass
  "did we miss anything?" critic. See TODO.
- **Package for the VM/Cody** — PyInstaller `.app` (arm64); the old kit installed *Claude
  Desktop* + the *meeting MCP* and is superseded by this app + `claude` CLI + gsuite-on-CLI.
- **Demote the `meeting` MCP in the docs** so future sessions don't assume it's central.

## Related state (today's other work)

- gsuite **Elevated → Internal OAuth app** done (`meeting-gsuite-internal`, 15 scopes) — this
  is what the brain routes through; see [[changelog]] + `~/.claude/plans/gsuite-oauth-internal-split.md`.
- `meeting-kit` **v0.1.1** released (Desktop tool-name fix). That kit targets the *old*
  MCP-in-Desktop model — it'll be superseded by the app packaging above.
