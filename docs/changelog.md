---
type: log
title: meeting — changelog
tags: [meeting, changelog]
related: [index]
---

# meeting — Changelog

Append-only. Newest on top. Written by `/log`.

## 2026-07-24 — Diarization progress made real + "Step N of M" counter

Lit up the last dark part of the diarize path and added an overall step indicator.

**What changed:**
- **Real diarization progress** — `trans_runner.py` now parses transd's `[diar] <step> c/t (p%)`
  lines (emitted when `TRANS_PROGRESS=1`, which trans_runner sets whenever a progress callback
  is active) → a determinate bar + ETA through pyannote's **segmentation** then **embeddings**
  steps. Previously an opaque throb. (The transd-side hook is logged in the `scripts` repo.)
  Proven on a live 90s run: `[diar] segmentation 0/82…100%`, `[diar] embeddings 1/8…100%`.
- **"STEP N OF M" counter** (`gui/app.py`) — a per-run, path-aware step indicator above the
  phase label. Built at start from URL-vs-file + diarize-on/off, so the total is always right:
  URL+diarize = 5 (download → segmentation → embeddings → transcribe → analyze); local file +
  fast = 2; pasted text = 1. pyannote's instant sub-steps (speaker_counting, clustering) are
  deliberately excluded — they'd flash by unperceived.

**Why:**
- Close the "how far in am I?" gap on the long diarize path (Joshua's request).

**Files modified:**
- `meeting/trans_runner.py` — `[diar]` parse + `TRANS_PROGRESS=1` env; `meeting/assistant/gui/app.py`
  — `_compute_steps`/`_phase_key`/`_update_step` + the STEP label.

**QA note:** sanity-checked the brain's extraction against a full diarized transcript (Point4
web-design meeting) — owners correct via diarization, date-anchoring correct, ambiguity flag
apt; only weakness is occasional **under-inclusion** (missed one real deliverable on a run),
which the review-before-create UX absorbs. Drove the new "completeness safety net" TODO.

---

## 2026-07-23 — Meeting Assistant GUI — built end-to-end + hardened through live testing

Built the standalone native app from the approved mockup, then hardened it across several
real-file test runs. Both paths (fast Whisper + diarized) now reach the review→create flow.

**What changed:**
- **GUI built** (`meeting/assistant/gui/`): `app.py` (setup → progress → review, three states),
  `worker.py` (thread + `queue.Queue` + cooperative Cancel, photoEditor pattern),
  `contacts_dialog.py` (in-app roster editor), `__main__.py`. Thin front-end over the existing
  `transcribe.transcribe()` + brain — no engine rewrite. Console script `meeting-assistant-gui`.
- **Structured brain** (`brain.py`): added `propose_structured()` (transcript → JSON action
  items for the editable review rows) + `create_items()` (creates only the approved rows via
  gsuite). Old free-text `route()` kept for the CLI.
- **Contacts / invite resolution** (`contacts.py`, new): name→email roster keyed by account,
  seeded with the Elevated team + their `@elevatedtrading.com` addresses; `me` identity per
  account (no self-invite). Editable in-app ("Manage guests…").
- **Progress streaming overhaul** — the recurring "no ETA" pain:
  - `PYTHONUNBUFFERED=1` on mlx_whisper so its segment lines stream → live **% + ETA** (they
    were block-buffered and never arrived until the end).
  - yt-dlp download streamed with `--newline` → **download %**.
  - `trans_runner.run()` now streams transd's stdout → **stage labels + "turn X/N"** on the
    diarize path (was a black box). Added `on_progress`/`stop_event` params (MCP path unaffected).
  - Progress callback contract changed to `(phase_label, fraction)`; GUI + CLI renderers updated.
  - GUI **wall-clock ticker** so opaque steps (pyannote diarization) read as working, not frozen.
- **Date-anchoring** (`brain.py` + GUI): a **Meeting date** field anchors relative-date
  resolution ("this Friday" → the Friday after the *meeting*, not today); auto-filled from a
  file's mtime.
- **arm64 fix** (`trans_runner.py` + `transcribe.py`): force `arch -arm64` on mlx_whisper /
  transd. Root cause of an exit-1 failure — MLX is arm64-only and crashed when the app ran under
  x86_64/Rosetta (`incompatible architecture`). Now immune regardless of launch arch. Detection
  computed once at import (`hw.optional.arm64`, honest under Rosetta; `platform.machine()` lies).
- **Dark-mode contrast**: theme-aware text colors (hardcoded light greys were invisible on dark).
- **Error reporting**: mlx_whisper failures now include the output tail (was bare "exit 1").
- **Cancel** works on both paths (`stop_event` threaded through whisper loop + trans_runner).
- **Dev launcher**: `MeetingAssistant.app` (gitignored) — double-click, no terminal, forces arm64.
- **Tests**: updated to mock `Popen` (streaming) instead of `run`; all 13 pass.

**Why:**
- Turn the proven CLI organs into the real product Joshua/Cody will use; fix every reliability
  gap surfaced by testing (buffered progress, wrong-date resolution, Rosetta crash, dark mode).

**Files modified:**
- new: `meeting/assistant/gui/{app,worker,contacts_dialog,__init__,__main__}.py`,
  `meeting/assistant/contacts.py`, `docs/meeting-assistant-design.md` (§ built), `MeetingAssistant.app`.
- edited: `meeting/assistant/{transcribe,brain,cli}.py`, `meeting/trans_runner.py`,
  `pyproject.toml`, `tests/test_transcribe.py`, `.gitignore`.

**Technical notes:**
- Diarization (pyannote) is a single opaque model pass — no honest sub-progress exists there;
  the ticker + stage label cover it. Real diarization progress would need pyannote's
  `ProgressHook` wired into the shared `~/scripts/bin/transd` (a follow-up).
- The GUI runs the repo `.venv` + live code (no rebuild while iterating). Native PyInstaller
  `.app` (for the VM/Cody) is still the eventual ship — build it under arm64 Python.

---

## 2026-07-21 — Meeting Assistant GUI — design settled + UI mockup approved

Design session ahead of building the native app (no code changed; decisions + a mockup).

**What changed:**
- Locked the **owner→invite routing model**: everything writes to the ONE account running
  the app; other people are added as **calendar guests** (Google invite → lands on their
  calendar, no login of theirs). Verified `gsuite calendar_create_event` supports
  `attendees` + `send_updates='all'` (`gsuite/tools/calendar_tools.py`).
- Surfaced the **Tasks-can't-have-guests asymmetry** → any item involving another person
  must be a Calendar **event** (undated → all-day); only your-own+undated stays a Task. Adds
  a **name→email map** need (seed from Elevated team roster, editable; no email → name-in-title).
- Locked the **GUI architecture**: thin front-end over the existing `transcribe.transcribe()`
  + `brain.route()`; photoEditor's thread + `queue.Queue` + `root.after` poll + `threading.Event`
  cancel pattern; `on_progress` callback already feeds the bar. New `assistant/gui/` package;
  copy photoEditor `build_app.sh`/`.spec`/`.icns` for packaging.
- Built + **approved a base UI mockup** (setup / progress / review-approve with invite chips)
  → artifact `https://claude.ai/code/artifact/5adf0c72-142e-41b5-b51e-acdcb2856f14`.
- Set **v1 scope**: quality segmented (Fast/Balanced/Best) + live ETA, speaker toggle,
  account dropdown, two-stage editable approve panel + invite chips, done-notification, Cancel.

**Why:**
- Nail the routing semantics + UI before writing Tkinter, so the build is mechanical.

**Files modified:**
- `docs/meeting-assistant-design.md` — new "GUI + routing design — SETTLED 2026-07-21" section.

**Next:** build `assistant/gui/{app.py,worker.py}` against the spec (morning).

---

## 2026-07-20 — [MAJOR/PIVOT] MCP-in-Desktop → standalone app + headless-Claude brain

A fresh-VM Desktop test exposed two fatal holes in the MCP model: (1) synchronous
`meeting_transcribe` **blocks/times out Claude Desktop** on any real-length meeting; (2) no
speaker labels → **can't route action items per owner**. Root cause: the slow heavy
transcription was living inside the interactive brain.

**Pivot:** a standalone local **Meeting Assistant app** (photoEditor pattern) owns
transcription with a **progress bar + ETA** and anti-hallucination flags; a **headless
`claude -p`** call (subscription auth, `ANTHROPIC_API_KEY=` — no API/cost, the `todo()`
pattern) is the brain that extracts action items and routes to Calendar/Tasks via the
**gsuite MCP**. The `meeting` MCP is **demoted off the critical path** (only `trans_runner`
survives, reused by the app). No new subscription — runs on the Max plan both already have.

**Built + proven end-to-end tonight** (dev machine): new `meeting/assistant/` package
(`transcribe.py`, `brain.py`, `cli.py`) + `meeting-assistant` console script. Audio clip →
clean transcript in 3s with live %/ETA, no hallucination loop; `claude -p` brain extracted 4
owner/date/Calendar-vs-Task items and flagged ambiguities; propose (safe default) + `--route`
both wired (`gsuite-elevated` ✔ on the CLI). Full design → `docs/meeting-assistant-design.md`.
**Still to do:** Joshua e2e test, `--diarize` verify, kit rework (CLI+gsuite-on-CLI, not
Desktop), native GUI wrapper, MCP-demotion docs — see TODO.md.

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
