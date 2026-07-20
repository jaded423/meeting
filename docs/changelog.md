---
type: log
title: meeting — changelog
tags: [meeting, changelog]
related: [index]
---

# meeting — Changelog

Append-only. Newest on top. Written by `/log`.

## 2026-07-20 — [FIX] tool names dotted → underscored (Claude Desktop rejected them)

**What changed:** renamed the two MCP tools `meeting.transcribe` → `meeting_transcribe` and
`meeting.status` → `meeting_status` (+ every reference in prompt text, settings strings,
tests, README, CLAUDE.md).

**Why:** first real Claude **Desktop** test (fresh VM, `meeting-kit` v0.1.0) failed with
`Unknown skill: meeting` + `tools.NN...name: String should match pattern ^[a-zA-Z0-9_-]{1,64}$`.
The server started and answered `tools/list` fine (log: `tools=['meeting.status',
'meeting.transcribe']`), but Desktop's frontend **rejects dotted tool names**, which poisoned
the whole server registration and dropped the `/meeting` prompt too. The 2026-07-09 unit tests
never caught it because they exercised the MCP protocol directly, not Desktop's validation.
gsuite (underscored) was unaffected. 13 tests still pass. Rebuilt kit + release `v0.1.1`.

## 2026-07-17 — [MAJOR] Fresh-Mac install kit built + published, then PAUSED

**What changed:**
- Built a self-contained **install kit** at `kit/`: `install.command` (zero→hero wizard —
  Command Line Tools → Homebrew → **Claude Desktop** → ffmpeg/yt-dlp → mlx-whisper venv →
  trans scripts → gsuite+meeting → Claude-Desktop registration → OAuth → **self-test**),
  `check_prereqs.command`, `register_desktop.py` (writes `claude_desktop_config.json`),
  `requirements.txt` (mlx-whisper pinned), `SETUP_MAC.md`, `build_kit.sh` (vendors
  meeting+gsuite+trans+oauth-client into `kit/vendor/`), `sample-meeting.txt` (a
  discrimination-test transcript: 2 dated events, 4 tasks, deliberate noise). `kit/.gitignore`
  keeps `vendor/` + `*.zip` out of the repo. Self-contained — installs from bundled copies,
  pulls nothing from git.
- Set up a reusable isolated test gsuite instance **`gsuite-brown`** (`~/.config/gsuite-brown`,
  authed to brown.joshua.david@gmail.com). See brain `gsuite-brown-test-instance`.
- **READMEs made public-facing** — broke gsuite's `README.md → CLAUDE.md` symlink (that's why
  it read like an internal doc) and wrote real public READMEs for both `gsuite` + `meeting`.
  NOT yet committed/pushed.
- **Secret-audited** gsuite + meeting (tree + full history) — clean. Flipped both **public**.
  Cut release `meeting-kit-v0.1.0` with `meeting-kit.zip`.

**Why PAUSED (Joshua, 2026-07-17):**
- The delivery reused the over-scoped **Elevated** OAuth client, which carries **restricted**
  Gmail scopes → Google's CASA verification wall, and bundling it into a public release exposed
  it (installed-app client → low-risk, but wrong). The verification/gatekeeping regime soured
  the approach → Joshua paused all Google/Meta/Anthropic-touching work.

**Open when resumed (detail in `TODO.md` ☀️ block):**
1. **Pull the public release** — it contains the exposed OAuth client.
2. **Build a lean calendar+tasks OAuth client** (sensitive, NOT restricted → no CASA wall,
   Production-publishable) instead of the Elevated Gmail one. The real fix.
3. **Reproducibility** — the zip was a one-off from local state; commit+push source, rebuild
   from a fresh clone, replace the asset.
- **The VM dry-run never ran** — the kit is untested on a fresh Mac.

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
