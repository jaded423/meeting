---
type: log
title: meeting — changelog
tags: [meeting, changelog]
related: [index]
---

# meeting — Changelog

Append-only. Newest on top. Written by `/log`.

## 2026-07-09 — [MAJOR] MCP core built (steps 4–5 of the baton plan)

**What changed:**
- Built the server package in `meeting/`: `server.py` (stdio MCP + `/meeting` prompt),
  `trans_runner.py` (subprocess bridge to `~/scripts/bin/{trans,transd}`), `settings.py`,
  `cli.py`, and `tools/` (`_registry.py`, `_errors.py`, `transcribe_tools.py`,
  `status_tools.py`). Plus `pyproject.toml`, `install.sh`, `tests/` (13 pass).
- **Surface = 2 tools + 1 prompt:** `meeting.transcribe` (audio/video file · yt-dlp URL ·
  or text-file passthrough → transcript), `meeting.status` (engine probe + settings readout),
  and the `/meeting` MCP prompt (transcribe → host Claude extracts action items → gsuite
  routes to Calendar dated / Tasks undated; honors the approval gate).
- **Settings layer** at `~/.config/meeting/settings.json` (`MEETING_CONFIG_DIR` override):
  `diarize_default=false`, `approval_gate=true`, `default_model=small`, `output_dir`.

**Why:**
- Cody's ask: `/meeting <mp3|url|txt>` in Claude Desktop → touchless meeting → calendar.
  Correct-minimal split: meeting does media→text only; gsuite routes, host Claude extracts.
- SOP authoring/rendering was **dropped** — it was an "inspo" pointer that got inflated across
  the trans→T0→meeting bounces; not part of the actual audio→text→calendar product.

**Files modified:**
- `meeting/**` - new server package
- `pyproject.toml`, `install.sh`, `.gitignore` - packaging + register + Python ignores
- `tests/**` - 13 tests (registry, transcribe, passthrough, settings, status)
- `CLAUDE.md` - status flipped to built; Surface section added

**Technical notes:**
- Verified end-to-end, not just mocked: `say`-generated clip → real `trans`/`mlx_whisper` →
  correct transcript in 4s ("Elevated Trading"/"Cody"/"Erica" correct, vocab bias live); text
  passthrough in 0.03s (skips Whisper). `meeting.status` shows all engines reachable on this box.
- Registered into the mcp hub's fleet scripts + wiki (see `~/projects/mcp/docs/changelog.md`).
- Remaining: Step 6 tail = distribute to Cody (blocked on his Mac specs + Plaud-vs-file);
  then T0 step 7 = global routing-map flip + `push-all`. Build is uncommitted.

---

## 2026-07-08 — [MAJOR] Project scaffolded

- Created `~/projects/meeting/` via `/newdir` (Tier-2 leaf under mcp).
- CLAUDE.md + docs/ + TODO.md seeded; git init (master); GitHub + Gitea remotes; registered in global routing map.
