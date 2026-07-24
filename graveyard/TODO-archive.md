# meeting — TODO archive

Completed `- [x]` items + superseded historical narrative swept out of `meeting/TODO.md`
(newest on top). Cold storage — durable record lives in the git history + the design docs
(`docs/meeting-assistant-design.md`, `~/projects/trans/docs/meeting-to-tasks-pipeline.md`).

---

## Completed — Meeting Assistant app (post-pivot, 2026-07-23/24)

- [x] **Test the `--diarize` (speaker-label) path.** `added 2026-07-20`. ✅ 2026-07-23 — runs on this machine (HF_TOKEN + pyannote present); streams stage + turn counter. Diarized owner-routing still to confirm on Create.
- [x] **Build the native GUI app — a real Apple app like photoEditor.** `added 2026-07-20`. ✅ 2026-07-23 — built (`meeting/assistant/gui/{app,worker,contacts_dialog}.py`) + hardened over several test runs (progress streaming, date-anchor, dark mode, arm64 fix, error tails, elapsed ticker, in-app contacts editor). Dev double-click launcher `MeetingAssistant.app` (gitignored). Design/gotchas → `docs/meeting-assistant-design.md`.
- [x] **Real diarization progress.** `added 2026-07-23`. ✅ 2026-07-24 — env-gated (`TRANS_PROGRESS=1`) custom hook in `~/scripts/bin/transd` prints clean `[diar] <step> c/t (p%)` lines; `trans_runner` parses → real determinate bar + ETA through segmentation + embeddings. Proven on a live run. Manual: `TRANS_PROGRESS=1 transd <url>`. Also added a "STEP N OF M" counter (per-run, path-aware).

## Completed — OAuth exposure fix (2026-07-17)

- [x] **🔴 #1 — LIVE EXPOSURE resolved 2026-07-17 (tonight).** Deleted release `meeting-kit-v0.1.0` + its tag; asset URL now 404s — the Elevated `oauth-client.json` is no longer downloadable anywhere public. Repos `meeting`+`gsuite` are still **public** but clean of secrets (audited) — flip to private if you want, optional. **When you reupload tomorrow, don't just re-cut the old zip** — go via #2/#3 (lean client + reproducible build) so the client exposure doesn't come right back.

## Completed — build phase (steps 4–6-register, all 2026-07-09)

- [x] **Build the MCP core + orchestration** — 2 tools + 1 prompt: `meeting.transcribe` (audio/URL/text→text), `meeting.status` (engine probe + settings), `/meeting` prompt (transcribe→extract→gsuite-route). Settings layer (`diarize_default=false`, `approval_gate=true`). 13 tests pass; real audio (4s) + text passthrough (0.03s) verified.
- [x] **Register-half of step 6** — `meeting` added to `mcp` `install-all.sh`/`sync-all.sh` `REPOS=`; mcp wiki index row + `components/meeting.md` added.

---

## Superseded historical narrative (kept for reference)

**⏸ (superseded) PAUSED 2026-07-17 (Joshua).** All Google/Meta/Anthropic-touching work paused — OAuth verification/CASA wall soured it. **Resolved 2026-07-20** via the Internal-app split; pause lifted. Kept for history.

### Built this session (2026-07-17) — the meeting-kit v0.1.x arch (superseded by the 2026-07-20 standalone-app pivot)

- **Install kit** at `~/projects/meeting/kit/`: `install.command` (zero→hero wizard — CLT→Homebrew→**Claude Desktop**→ffmpeg/yt-dlp→mlx-whisper venv→trans scripts→gsuite+meeting→Claude-Desktop registration→OAuth→**self-test**), `check_prereqs.command`, `register_desktop.py`, `requirements.txt` (mlx-whisper pinned), `SETUP_MAC.md`, `build_kit.sh`, `sample-meeting.txt`. Self-contained (installs from bundled `vendor/`, pulls nothing from git); idempotent; `kit/.gitignore` keeps `vendor/`+`*.zip` out of the repo.
- **READMEs rewritten public-facing** — broke gsuite's `README.md → CLAUDE.md` symlink (that's why it read internal); real public READMEs now for both `gsuite` + `meeting`.
- gsuite + meeting **secret-audited CLEAN** (tree + full history), flipped **public**, release cut (→ see #1 exposure).
- **NEVER RAN: the VM dry-run** — the kit was untested on a fresh Mac.
