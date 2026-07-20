# meeting

> **Stack:** Tier-2 leaf. Parent: [mcp](~/projects/mcp/CLAUDE.md). Router: [global](~/.claude). Tier convention: [wiki-rollout-plan](~/.claude/docs/wiki-rollout-plan.md).

## Purpose

Transcription MCP — packages the `trans` stack (audio/URL/file → transcript) as Claude-usable tools; Cody's Claude handles extraction → Google Calendar/Tasks routing.

## Status

**Core BUILT 2026-07-09** (mcp session; steps 4–5 of the baton plan). Server package in `meeting/`; 13 tests pass; transcribe + text-passthrough + status all verified on real input. **Remaining = step 6** (register in `mcp` `install-all.sh` `REPOS=` + distribute to Cody + global routing-map register — that last is T0's step 7). Open Qs for Cody: Mac specs + Plaud-device-vs-file input.

**Design doc (the what/why/how, engine bench, routing, human-in-loop):** [`~/projects/trans/docs/meeting-to-tasks-pipeline.md`](~/projects/trans/docs/meeting-to-tasks-pipeline.md). Delivery = 2 MCPs on Cody's Claude Desktop (`meeting` transcribes + `gsuite` routes to Calendar/Tasks); Cody's Claude = the extraction brain. Peer of `gsuite`/`leadscout` under the `mcp` hub; uses `trans`, not org-coupled to it. Baton plan: [`~/.claude/plans/meeting-mcp-build.md`](~/.claude/plans/meeting-mcp-build.md).

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
