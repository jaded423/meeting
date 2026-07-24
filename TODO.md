# meeting — TODO

> Session handoff lives here. Keep priority-ordered — first open item = what's next.
> Cross-project / no-single-home tasks go to `~/.claude/TODO.md`, not this file.
> Completed items + superseded history → [graveyard/TODO-archive.md](graveyard/TODO-archive.md).

> **Design doc = [`~/projects/trans/docs/meeting-to-tasks-pipeline.md`](~/projects/trans/docs/meeting-to-tasks-pipeline.md).** Build from the `mcp` session, from this dir.
> **Cross-owner plan (baton: T0 → trans → mcp → T0) = [`~/.claude/plans/meeting-mcp-build.md`](~/.claude/plans/meeting-mcp-build.md).** Step 0 ✅ (T0 route) · 1–3 ✅ (trans) · 4–5 ✅ + 6 register-half ✅ (mcp) · **6 tail ⬜ (Cody, blocked)** · **7 ⬜ (T0 wrap, ready)**.

> **▶ RESUMED + PIVOTED 2026-07-20 (Joshua).** OAuth wall solved (Elevated → Internal app). A fresh-VM test then forced an architecture pivot: **MCP-in-Desktop → standalone app + headless-`claude` brain.** Full design → [`docs/meeting-assistant-design.md`](docs/meeting-assistant-design.md).

**Fathom/trans/meeting classification (settled 2026-07-08):** `trans` = transcription engine · `fathom` = intake harness (URL source, NOT folded in) · `loom` retired, `plaud` deleted · `meeting` = this MCP wrapping trans. Real product = audio→text→calendar/tasks.

## ⭐ Meeting Assistant app (post-pivot) — in shakeout

GUI app **BUILT + hardened through live testing 2026-07-23** (`meeting/assistant/gui/`). Both fast + diarized paths reach the review→create flow. Remaining:

- [ ] **Shakeout: run the full flow to a live calendar.** `added 2026-07-20`. Confirm the review-panel **Create** actually lands events/tasks + emails invites per owner; both paths; then decide it's solid.
      resume: App works end-to-end via `python -m meeting.assistant.gui` (or the dev `MeetingAssistant.app`). Fast path: live %/ETA ✔. Diarize path: runs, shows stage + "turn X/N" ✔ (ticking elapsed added). Meeting-date field anchors relative dates ✔. arm64 crash FIXED (MLX arm64-only; `arch -arm64` forced). NOT yet done: press **Create** on a real review and verify the events/tasks/invites land; confirm diarized owners route correctly.
- [ ] **Completeness safety net — catch action items the brain missed, esp. for meetings Joshua wasn't in.** `added 2026-07-24`. Problem (Joshua, 2026-07-24): for a meeting he didn't attend he has no ground truth to notice a dropped item — and the brain tends to occasional under-inclusion (a real Luis "four-pillars design" deliverable was missed on one run). Ideas, in order of effort:
      (a) **Email the full diarized transcript** to a configurable address (a "email transcript to ___" field on the review screen / in settings) — a reviewable audit backup so the raw source is always recoverable. Joshua's proposed quick partial win. Uses gsuite `gmail_send_message` (or the brain's create step).
      (b) **Second-pass "did we miss anything?" critic** — a separate `claude -p` pass over the transcript prompted to find agreed commitments the first pass skipped; surface candidates in the review panel (opt-in, unchecked). The completeness-critic pattern.
      (c) Consider showing a confidence/coverage note (e.g. "N speakers, M topics, K items — review if that seems low").
- [ ] **Package for the VM/Cody — PyInstaller `.app`.** `added 2026-07-20`. Build under **arm64 Python** (MLX). Supersedes `meeting-kit` v0.1.x (that installed Claude *Desktop* + the *meeting MCP*); new arch = the `.app` + `claude` CLI + gsuite-on-CLI. Then Cody-settings timed run on the VM (M3 Pro / 18 GB).
- [ ] **Demote the `meeting` MCP in docs.** `added 2026-07-20`. Partial 2026-07-23 (meeting `CLAUDE.md` now leads with the app). Left: the global routing-map line in `~/.claude/CLAUDE.md` still calls meeting an MCP — update on a /sum pass.

## OAuth distribution follow-ups

- [ ] **🔑 #2 — Internal-split OAuth fix (Point4 side still open).** `added 2026-07-17`. Plan: [`~/.claude/plans/gsuite-oauth-internal-split.md`](~/.claude/plans/gsuite-oauth-internal-split.md). Internal apps are CASA-exempt even with restricted Gmail scopes, so the fix is Internal clients (full scope) for Elevated+Point4. Public kit is safe because Internal rejects non-org accounts. **Elevated done 2026-07-20**; next action = verify Cody's org account + Point4 Workspace, then cut the Point4 Internal client.
- [ ] **⚠️ #3 — Reproducibility: the shipped zip was a one-off from local state.** `added 2026-07-17`. `meeting-kit.zip` was built by `build_kit.sh` from Joshua's **local working tree** (uncommitted `kit/`, README edits) — the public repos are stale, so **nobody could regenerate the release from public source.** Correct order when resumed: (a) commit + push all `meeting`+`gsuite` source; (b) rebuild the zip from a **fresh clone** (proves reproducibility); (c) replace the release asset. Caveat: `oauth-client.json` comes from local `~/.config/` (not any repo, correctly) → clean-clone build needs the client supplied separately — which #2 makes clean. *(Superseded by the standalone-app pivot if PyInstaller packaging replaces the kit entirely — re-scope when the Package item lands.)*

## Deferred

- [ ] **Distribute to Cody (BLOCKED on Cody).** `added 2026-07-08`. Needs his Mac specs (M-series? RAM) + Plaud-device-vs-audio-file capture answer.
