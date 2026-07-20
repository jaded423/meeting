# meeting — TODO

> Session handoff lives here. Keep priority-ordered — first open item = what's next.
> Cross-project / no-single-home tasks go to `~/.claude/TODO.md`, not this file.

> **Design doc = [`~/projects/trans/docs/meeting-to-tasks-pipeline.md`](~/projects/trans/docs/meeting-to-tasks-pipeline.md).** Build from the `mcp` session, from this dir.
> **Cross-owner plan (baton: T0 → trans → mcp → T0) = [`~/.claude/plans/meeting-mcp-build.md`](~/.claude/plans/meeting-mcp-build.md).** Step 0 ✅ (T0 route) · 1–3 ✅ (trans) · 4–5 ✅ + 6 register-half ✅ (mcp) · **6 tail ⬜ (Cody, blocked)** · **7 ⬜ (T0 wrap, ready)**. Tick your owned steps there; volatile state = its `resume-here`.

> **⏸ PAUSED 2026-07-17 (Joshua).** All Google/Meta/Anthropic-touching work paused indefinitely — the OAuth verification/gatekeeping regime (restricted Gmail scopes → CASA wall) soured the whole approach. Nothing here is urgent; resume from the ☀️ block when/if you want.

**Fathom/trans/meeting classification (settled 2026-07-08):** `trans` = transcription engine · `fathom` = intake harness (URL source, NOT folded in) · `loom` retired, `plaud` deleted · `meeting` = this MCP wrapping trans. Real product = audio→text→calendar/tasks.

### ☀️ MORNING PICKUP — start here, in order

- [x] **🔴 #1 — LIVE EXPOSURE resolved 2026-07-17 (tonight).** Deleted release `meeting-kit-v0.1.0` + its tag; asset URL now 404s — the Elevated `oauth-client.json` is no longer downloadable anywhere public. Repos `meeting`+`gsuite` are still **public** but clean of secrets (audited) — flip to private if you want, optional. **When you reupload tomorrow, don't just re-cut the old zip** — go via #2/#3 (lean client + reproducible build) so the client exposure doesn't come right back.
- [ ] **🔑 #2 — THE REAL FIX → superseded by the Internal-split plan (2026-07-20): [`~/.claude/plans/gsuite-oauth-internal-split.md`](~/.claude/plans/gsuite-oauth-internal-split.md).** Internal apps are CASA-exempt even with restricted Gmail scopes, so the fix is Internal clients (full scope) for Elevated+Point4, not a lean calendar+tasks client. Public kit is safe because Internal rejects non-org accounts. Next action = verify Cody's org account + Point4 Workspace. Old lean-client note below kept for context. `added 2026-07-17`. The entire verification/exposure mess came from shipping the over-scoped **Elevated** client, which drags **restricted** Gmail scopes → CASA verification wall. `meeting` only needs **`calendar` + `tasks`** — those are **sensitive, NOT restricted** → no CASA, no wall, and such a client can even be **Published to Production** (no 7-day expiry, no "unverified app" warning, far safer to distribute). Make a dedicated GCP project + Desktop OAuth client requesting ONLY calendar+tasks; point the kit's gsuite instance at that. This is the correct distribution primitive and dissolves both #1 and the whole rant.
- [ ] **⚠️ #3 — Reproducibility: the shipped zip was a one-off from local state.** `added 2026-07-17`. `meeting-kit.zip` was built by `build_kit.sh` from Joshua's **local working tree** (uncommitted `kit/`, README edits) — the public repos are stale, so **nobody could regenerate the release from public source.** Correct order when resumed: (a) commit + push all `meeting`+`gsuite` source; (b) rebuild the zip from a **fresh clone** (proves reproducibility); (c) replace the release asset. Caveat: `oauth-client.json` comes from local `~/.config/` (not any repo, correctly) → clean-clone build needs the client supplied separately — which #2 makes clean.

### Built this session (2026-07-17) — kept on disk, but see caveats above

- **Install kit** at `~/projects/meeting/kit/`: `install.command` (zero→hero wizard — CLT→Homebrew→**Claude Desktop**→ffmpeg/yt-dlp→mlx-whisper venv→trans scripts→gsuite+meeting→Claude-Desktop registration→OAuth→**self-test**), `check_prereqs.command`, `register_desktop.py`, `requirements.txt` (mlx-whisper pinned), `SETUP_MAC.md`, `build_kit.sh`, `sample-meeting.txt`. Self-contained (installs from bundled `vendor/`, pulls nothing from git); idempotent; `kit/.gitignore` keeps `vendor/`+`*.zip` out of the repo.
- **READMEs rewritten public-facing** — broke gsuite's `README.md → CLAUDE.md` symlink (that's why it read internal); real public READMEs now for both `gsuite` + `meeting`. **NOT committed/pushed** → GitHub still shows the old ones.
- gsuite + meeting **secret-audited CLEAN** (tree + full history), flipped **public**, release cut (→ see #1 exposure).
- **NEVER RAN: the VM dry-run** — the kit is untested on a fresh Mac. That was the whole point and it didn't happen.

### Deferred (was next before the pause)

- [ ] **Distribute to Cody (BLOCKED on Cody).** `added 2026-07-08`. Needs his Mac specs (M-series? RAM) + Plaud-device-vs-audio-file capture answer.

## Done (build phase — steps 4–6-register, all 2026-07-09)

- [x] **Build the MCP core + orchestration** — 2 tools + 1 prompt: `meeting.transcribe` (audio/URL/text→text), `meeting.status` (engine probe + settings), `/meeting` prompt (transcribe→extract→gsuite-route). Settings layer (`diarize_default=false`, `approval_gate=true`). 13 tests pass; real audio (4s) + text passthrough (0.03s) verified.
- [x] **Register-half of step 6** — `meeting` added to `mcp` `install-all.sh`/`sync-all.sh` `REPOS=`; mcp wiki index row + `components/meeting.md` added.
