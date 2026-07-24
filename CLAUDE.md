# meeting

> **Stack:** Tier-2 leaf. Parent: [mcp](~/projects/mcp/CLAUDE.md). Router: [global](~/.claude). Tier convention: [wiki-rollout-plan](~/.claude/docs/wiki-rollout-plan.md).

## Purpose

Turn a meeting recording (audio/URL/pasted text) into Google Calendar events + Tasks. Local
Whisper transcribes; a headless `claude -p` brain extracts action items; you review/edit them
(with per-person invite chips) before anything is created.

## Status — the STANDALONE APP is the product (pivoted 2026-07-20)

**`meeting/assistant/` is the real deliverable**, not the MCP. A native Tk GUI drives local
transcription (progress + ETA) → structured proposal → an editable review panel → create via
gsuite. **Built + hardened through live testing 2026-07-23** (both fast + diarized paths reach
the review→create flow; 13 tests pass). Run: `python -m meeting.assistant.gui`, or double-click
the gitignored dev `MeetingAssistant.app`. **Must run arm64** (MLX is arm64-only — forced via
`arch -arm64`; the eventual PyInstaller `.app` must be built under arm64 Python). Design + the
testing gotchas: [docs/meeting-assistant-design.md](docs/meeting-assistant-design.md).

Remaining: Joshua shakeout on a live calendar → Cody VM timed run → PyInstaller packaging (see
[TODO.md](TODO.md)). Contacts roster (name→email for invites) is editable in-app or at
`~/.config/meeting-assistant/contacts.json`.

**The `meeting` MCP (below) is now OFF the critical path** — nothing in the app calls it; only
`trans_runner.py` is reused. Kept as an optional "transcribe from a chat" convenience.
Historical design/pivot: [docs/meeting-assistant-design.md](docs/meeting-assistant-design.md);
older MCP-build baton plan: [`~/.claude/plans/meeting-mcp-build.md`](~/.claude/plans/meeting-mcp-build.md).

## Surface (what it exposes)

Correct-minimal: `meeting` only does media→text; **gsuite** owns Calendar/Tasks routing, the **host Claude** owns extraction.

- **`meeting_transcribe`** (tool) — audio/video file · yt-dlp URL · or text file (`.txt/.srt/…` → passthrough, skip Whisper) → transcript. Wraps `~/scripts/bin/{trans,transd}` (`trans_runner.py`). Args: `diarize`, `model`, `name`, `output_dir`, `include`, `timeout` — omitted ones fall back to settings.
- **`meeting_status`** (tool) — engine reachability (trans/transd/mlx_whisper/yt-dlp) + settings readout with flip-instructions. Call first when transcription fails.
- **`/meeting <input>`** (MCP *prompt*, surfaces as a slash command in Claude Desktop) — the orchestration: transcribe → host Claude extracts agreed action items → routes via gsuite (`calendar_create_event` dated · `tasks_create` undated). Honors the approval gate.
- **Settings** — `~/.config/meeting/settings.json` (`MEETING_CONFIG_DIR` override): `diarize_default=false`, `approval_gate=true`, `default_model=small`, `output_dir`. install.sh writes a default; edit + see them via `meeting status`.

## Layout

- `docs/` — typed-frontmatter notes (Tier-2 = notes only, no `wiki/`). Start at [docs/index.md](docs/index.md).
- `docs/changelog.md` — append-only history (`/log` writes here).
- `TODO.md` — open tasks + the session handoff (keep priority-ordered; first open item = what's next).

## Conventions

Keep THIS file lean + current-operational; cold content (history, design, build logs) → a typed `docs/*.md` this file points at. Memory homes + the one-home rule: [memory-architecture](~/.claude/docs/memory-architecture.md). This project's routing-map line lives in the global [CLAUDE.md](~/.claude/CLAUDE.md) "Active Projects" under **AI / Claude tooling**.
