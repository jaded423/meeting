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

**▶ Next session (2026-07-26), in this order** — all four decided with Joshua 2026-07-25, no re-litigating:
1. ~~**gsuite all-day + `send_updates` fixes**~~ — **DONE early, 2026-07-25**, shipped + live-verified ([`gsuite/docs/changelog.md`](~/projects/gsuite/docs/changelog.md)). Start at #2. **No restart chore for the app** — it shells out to `claude -p` (`brain.py:109`), which spawns fresh MCP servers per run, so it already gets the new module. Only long-lived sessions (an open Claude Code session, Claude Desktop) hold the stale one.
2. ~~**Event-default + the 9:00am time dropdown**~~ — **BUILT 2026-07-27**, 87 tests pass. Mechanical half proven; the prompt half (does the model actually prefer `event`?) needs one live run — see the item below.
3. ~~**Structured CREATED section** + **guests into task `notes`** + **email-tick defaults ON**~~ — **DONE 2026-07-27**, all three.
4. ~~Joshua re-tests~~ — **partly done 2026-07-27** (that run is what exposed the wrong-account bug). Still unread off a run: the double-send check, and whether the model now prefers `event`.

**▶ PRIORITY RESET 2026-07-27 (Joshua): a standalone app that needs no terminal.** The packaging item is now the first open item below, ahead of the remaining shakeout/polish work. Rationale in his words: *"let's bump the item up in the todo to where we can have an app that does not need a terminal to run."*
> ⚠ Read the item carefully before starting — **"no terminal" is already half-true.** `MeetingAssistant.app/Contents/MacOS/` is a dev launcher that double-clicks open with no terminal window (it forces `arch -arm64`, MLX being arm64-only). What it still needs is the **repo + `.venv` present at `~/projects/meeting`**, so it is a launcher, not a distributable. The real gap is the PyInstaller bundle + the `install.command` steps below — not the terminal itself.

- [ ] **Package for the VM/Cody — PyInstaller `.app`.** `added 2026-07-20`. Build under **arm64 Python** (MLX). Supersedes `meeting-kit` v0.1.x (that installed Claude *Desktop* + the *meeting MCP*); new arch = the `.app` + `claude` CLI + gsuite-on-CLI. Then Cody-settings timed run on the VM (M3 Pro / 18 GB).
      resume: 2026-09-09 — deltas (1) and (2) are now TRUE on Cody's REAL Mac, not just the
      VM: he installed Claude Code (Ghostty) + Claude Desktop + gsuite (full features,
      prompt-gated, registered at BOTH CLI user scope and Desktop) from gsuite/INSTALL.md
      unattended, tests verified. Brain `cody-gsuite-install`. Remaining = the `.app` build itself.
      **Delta from the proven-on-VM state (settled 2026-07-24)** — everything else was already validated there under Claude Desktop:
      (1) **`claude` CLI installed + `claude auth login`** on Cody's own Max account. This is the only genuinely new dependency; `brain.py` blanks `ANTHROPIC_API_KEY` so it always resolves to the subscription — no API key, nothing to configure. ✅ Made self-service 2026-07-24 (`auth.command` + pre-flight; see changelog).
      (2) **Re-register gsuite at CLI user scope** (`claude mcp add … -s user`). Desktop and the CLI keep MCP config in *different* stores, so this is a second registration — but the **same** server and the **same** Google OAuth grant in `~/.config/gsuite-<acct>/`, so the VM's OAuth proof still stands. Keep the Desktop registration too: Cody uses full gsuite from Desktop, the app taps gsuite via the CLI.
      (3) **Drop the `meeting` MCP** — the app replaced it; it does not get installed.
      **→ Fold (1) and (2) into `kit/install.command`** (NOT `install.sh`). Joshua, 2026-07-24 — his framing, gathered from across the session; quotes trimmed, `[bracketed]` bits are mine:
      > "I feel like we need to take 1-3 and wrap it into the install.command? (well, drop #3, but add the other two) We would need to look into that q about the install.sh, but I think install.command ended up superceding it as it installs xcode cli tools and then on second run it installs everything else, including checking if claude desk is installed, now will need to install claude cli, but wrap all of this into the todos"
      > "So I need to register it with cli AND desk so he can use the full gsuite from desk mcp, and the meeting assist through the app that taps cli."
      > "He will need to install the stack [= everything already tested on the VM] ... now, we are invoking claude, so he needs claude cli instead of desk, but I have already proven gsuite tests with other logins in VM."
      **Next session — start here, nothing below was investigated:**
      - `kit/install.command` = the installer of record (10 steps, idempotent, self-testing; 2-pass — step 1 installs Xcode CLT then tells you to re-run; already checks for Claude **Desktop**). Confirm it supersedes both `meeting/install.sh` and `kit/vendor/*/install.sh`, and retire whatever it replaces.
      - **Add a step: install Claude Code CLI** (`npm install -g @anthropic-ai/claude-code`) alongside the existing Desktop check — same idempotent check-before-install shape as the other steps. Bump `TOTAL`.
      - **Add a step: sign in** — `claude auth login`, or just generate + point at `~/.config/meeting-assistant/auth.command` (already built; `brain.ensure_auth_command()`).
      - **Add a step: register gsuite at CLI user scope**, keeping the Desktop registration. **Open q (uninvestigated):** does `gsuite/install.sh` already do the `-s user` CLI registration or is it Desktop-only? Decides whether install.command re-runs it or issues `claude mcp add … -s user` itself.
      - Verify the installer's self-test covers the CLI path (`claude auth status --json` → `loggedIn`), not just Desktop.
- [x] **Finder-launched app can't see `claude` ("not installed" on a Mac where it is).**
      `added 2026-07-28`. **DONE 2026-07-28, 105 tests pass.** Found by Joshua on the first
      double-click run. Cause: a GUI launched by LaunchServices (**double-click *and* `open`
      — both**) inherits launchd's minimal `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, never the
      shell's, so `~/.local/bin/claude` is invisible; `brain.auth_status()` gets
      `FileNotFoundError` and reports "isn't installed". `ffprobe` (drives the ETA) was
      equally invisible. Fix: `trans_runner.ensure_path()`, called first thing in
      `gui/app.py:main()`. Deliberately **not** a new dir list — `_PATH_EXTRA` +
      `_augmented_env()` already had the right dirs and were only ever applied to *child*
      processes; this points the same knowledge at the interpreter itself. Verified by
      reproducing the exact env (`env -i` + minimal PATH): before = `installed=False`, after
      = `ok=True installed=True 'claude.ai'`.
      ⚠ **This bug made every prior "successful" run terminal-launched** — i.e. the app has
      never actually been exercised the way Cody will run it. Worth remembering when reading
      old "verified live" notes, same lesson as the wrong-account bug.
      ⚠ *Bisect artifact worth not re-discovering:* the Claude CLI's keychain lookup keys on
      **`$USER`** — strip it and `auth status` says `loggedIn:false` even with a good PATH.
      A real Finder launch **does** pass `USER`/`HOME`/`LOGNAME` (only `PATH` is minimal), so
      this is a testing trap, not a shipping bug. Don't "fix" it.
- [x] **Move `HF_TOKEN` out of the shell into `~/.secrets/hf_token` (Joshua's action).** DONE 2026-07-28 (file 600 present, rotated; no `export HF_TOKEN` in any zshrc — verified on the Pocket 2026-09-19)
      `added 2026-07-28`. App-side plumbing is DONE (item below); this is the one manual step.
      **The old token was leaked into a session transcript 2026-07-28 and must be rotated** —
      same failure mode as the Anthropic key on 2026-07-10, and the same fix: a file, not a
      shell export. Rotate at <https://hf.co/settings/tokens> (read scope), then, in a plain
      terminal (NOT through Claude, so the value never enters a transcript):
      `mkdir -p ~/.secrets && umask 077 && read -rs HF && printf '%s' "$HF" > ~/.secrets/hf_token && unset HF`
      Then drop the `export HF_TOKEN=` line from `~/.zshrc.local` — the file is read by both
      launch paths, so the export is now redundant *and* is the thing that leaks.
      verify: test -s ~/.secrets/hf_token && ! grep -q HF_TOKEN ~/.zshrc.local && echo CLEAN
- [x] **Diarize fails under a Finder launch — `transd` exit 1, "HF_TOKEN required".**
      `added 2026-07-28`. **DONE 2026-07-28, 110 tests pass.** Second bug of the same family
      as the PATH one, found immediately after it: `HF_TOKEN` is a `~/.zshrc.local` export,
      and a Finder-launched app never sources a profile, so `_augmented_env()` (which is just
      `os.environ` + PATH) handed transd nothing and pyannote's gated models were unreachable.
      Fix: `trans_runner.hf_token()` — env first, then `~/.secrets/hf_token`, then
      `~/.cache/huggingface/token` (the `huggingface-cli login` location, so Cody can use the
      normal HF flow) — injected in `_augmented_env()`, which is the choke point every child
      already goes through. Plus a **pre-flight**: diarize with no token now raises a clean
      actionable TransError *before* launching, instead of exiting 1 thirty seconds later; and
      the error tail is ANSI-stripped (`_ANSI`) because transd's colour codes were reaching
      the GUI dialog as literal `[0;31m`. Terminal path re-verified unchanged.
      **Standing lesson, third instance today:** anything the app reads from the *shell*
      (PATH, HF_TOKEN, …) is absent under the launch method users actually use. Audit for a
      4th before shipping — `env -i HOME=$HOME USER=$USER PATH=/usr/bin:/bin` is the repro.
- [ ] **Shakeout: run the full flow to a live calendar.** `added 2026-07-20`. Confirm the review-panel **Create** actually lands events/tasks + emails invites per owner; both paths; then decide it's solid.
      resume: App works end-to-end via `python -m meeting.assistant.gui` (or the dev `MeetingAssistant.app`). Fast path: live %/ETA ✔. Diarize path: runs, shows stage + "turn X/N" ✔ (ticking elapsed added). Meeting-date field anchors relative dates ✔. arm64 crash FIXED (MLX arm64-only; `arch -arm64` forced). **Create 2026-07-25: PARTIAL SUCCESS — it looked like a clean pass, and wasn't.** (run `jpJSs2N…`, URL input): transcribe → 18 topics / 12 items → picked 2 → both landed. What was genuinely proven: the event carried both guests and really emailed the invites, the task landed with its due date, the audit email + 18 KB attachment arrived. What was NOT proven, and looked fine because nothing in the app or the logs said otherwise: **the destination**. Discovered 2026-07-27 — that run wrote to **jaded423, not Elevated**. Every success signal was real; they were just about the wrong calendar, which is exactly why it passed review. Wrong-account items deleted 2026-07-27, root cause fixed same day (see changelog). **Treat the account half as unverified until a post-fix run proves it** — and read this as the standing lesson: "it worked" is not the same as "it worked where I meant it to." The **event** got both guests attached and invites really emailed (`send_updates="all"`; Calendar: "2 guests · 2 awaiting") ✔; the **task** landed with its due date ✔; audit email + 18 KB transcript attachment arrived ✔. Guest addresses were typed by hand **on purpose** — test phase, Joshua's own accounts only, so no real invites go to the agency. NOT yet done: **confirm diarized owners route correctly** (auto-resolve is only exercised when diarization names a speaker *and* `contacts.json` knows them; unknown names blank out for one-off inline entry, which is intended behaviour, not a gap).
- [x] **Completeness safety net — catch action items the brain missed, esp. for meetings Joshua wasn't in.** `added 2026-07-24`. **DONE 2026-07-25 — all three parts built 07-24, live-verified 07-25** (run `jpJSs2N…`: email + attachment landed; ledger read `18 topics · 12 items · 4 ⚠ missed`; the 2nd pass contributed 4 `[2nd pass]` candidates, all correctly unchecked, and the 9 skipped rows are recorded in the email). Pass 1 caught the Luis four-pillars deliverable unaided this run. Two follow-ups it exposed are separate items below (router prose in the email body; two identical emails 59 s apart). Problem (Joshua, 2026-07-24): for a meeting he didn't attend he has no ground truth to notice a dropped item — and the brain tends to occasional under-inclusion (a real Luis "four-pillars design" deliverable was missed on one run).
      (a) ✅ **Email the transcript** — checkbox + address (defaults to the account's own) and a "Send now" button on the review screen; `brain.email_transcript()` sends via gsuite `gmail_send_message` with the transcript as a **file attachment** (by path — never through a model's context) and the coverage report as the body. The report lists **skipped** rows too — the half Calendar can't tell you later.
      (b) ✅ **Second-pass critic** — `brain.audit_coverage()`: a fresh `claude -p` that re-reads the transcript knowing what pass 1 caught, is told pass 1 under-includes, and breaks ties toward "missed". Candidates land in the review list **unchecked**, tagged `⊕ 2nd pass`. Setup toggle "Double-check for missed items" (default ON).
      (c) ✅ **Coverage ledger** — `N speakers · M topics · K items` + `⚠ N missed` with an expandable per-topic list (`covered` / `no-action` / `missed`).
      resume: Code + 26 unit tests + Tk render smoke-tests all pass (39 tests total). **First live send 2026-07-24 — the email landed ✔** (transcript + report to joshua@elevatedtrading.com); it exposed 2 bugs, both now fixed (dateless-event guard + single email path — see changelog). Still NOT verified: (1) does the 2nd pass actually catch a known-dropped item — replay the Luis "four-pillars" recording, the one case with ground truth; (2) do the created events/tasks/invites actually land (the run that sent the email created nothing — the router refused the dateless events); (3) is the topic ledger's granularity useful or noisy on a long meeting.
- [ ] **Default action items to EVENTS; task only as fallback.** `added 2026-07-25`. Joshua's call, 2026-07-25: *"The default is to event, with fallback as task when lack of criteria blocks it. We want event defaults so it CAN tag those involved. And we are already able to exclude/add in the UI, so we get a last say before it ships."* Today's rule is the inverse — a dated deliverable becomes a `task`, and Tasks has no attendee field, so every notify path dies (proved 07-24: 3 tasks created, `Only me`, nobody told). Change `_PROPOSE_JSON` + `_AUDIT_JSON` (`brain.py`) to prefer `event` whenever a date is derivable; `task` only when there is none. Keep the dateless-event guard (`_row_problem`) — with the default flipped it becomes the "add a date to invite X" nudge instead of a silent demotion. **Dependency CLEARED 2026-07-25** — the gsuite fix shipped and is live-verified, so nothing gates this now. What the tool accepts today: `2026-07-28` → all-day, `2026-07-28T09:00` → timed, auto-stamped `America/Chicago` from the calendar (the app sends a wall-clock time and knows nothing about zones), `end` optional → `duration_minutes` default 30 = the 9:00–9:30 the dropdown wants. Attendees are emailed unless `send_updates='none'` is passed explicitly. ⚠ One assumption to revisit while editing: `test_review_validation.py` and `gui/app.py:653` both encode *"`calendar_create_event` requires start/end"* — no longer true. The dateless-event guard (`_row_problem`) is still wanted, but its rationale changes from "the API will reject this" to "a dateless item can't carry an invite", so keep it as the *nudge* Joshua described, not a hard block.
      resume: **Code DONE 2026-07-27, 87 tests pass** — see [changelog](docs/changelog.md). Both prompts flipped to event-default; time picker shipped (half-hour slots + explicit **All day**, default **9:00 AM**, greys out on a Task); `_split_when`/`_join_when` emit `YYYY-MM-DD HH:MM` or bare `YYYY-MM-DD` with no timezone. Guard kept — a date is still mandatory for an event, so it now reads as the "add a date to invite X" nudge. **Still open: does the model actually obey the new rule?** A prompt change can't be unit-tested — needs one live run (#4 above). Watch for: items that should be events still coming back as `task`, and whether 9:00 AM feels right or wants to be per-item smarter.
      **+ Time-of-day dropdown — Joshua, 2026-07-25:** *"Could we add a time option, and just default to 9:00am with a dropdown? Once the gsuite is fixed to handle it of course."* So each event row gets an editable time, **default 09:00** (→ a normal 30-min 9:00–9:30 event), with the dropdown offering the usual half-hour slots plus an explicit **All day** choice. That makes the common case a clean timed event rather than a 24-hour bar, and keeps all-day as a deliberate pick — which is exactly why the gsuite `{"date": …}` branch is still needed underneath, not bypassed by the 9am default.
- [ ] **`point4.me.email` is blank in `contacts.json`.** `added 2026-07-25`. Narrow leftover from the roster discussion — the *resolver* is *not* a bug and needs no work (**Joshua, 2026-07-25: working as intended** — blanks out an attendee it doesn't know, add inline as a one-off or to the roster if frequent; adding Luis/Cesar is his call, not a code task). What is worth a line: `point4.me` has `"email": ""`, and the email target defaults to the account's own address — so a run on the point4 account has nothing to default to. Fill it, or confirm the app fails loudly rather than silently skipping the audit email.
      verify: python -c "import json;print(json.load(open('$HOME/.config/meeting-assistant/contacts.json'))['point4']['me']['email'] or 'BLANK')"
- [x] **The audit email must not carry the router's prose.**
      **DONE 2026-07-27** — `create_items()` returns structured per-item results;
      `format_created()` renders them (`✓ action · date · Event/Task · invited …`,
      `✗ NOT created — … · why`). Router prose stays in `raw_result.output` / the log.
      verify: grep -q 'def format_created' meeting/assistant/brain.py && echo WIRED
      `added 2026-07-25`. **Approved 2026-07-25** ("Sounds perfect"). Joshua, 2026-07-25: *"you also added other things to the email lol."* The CREATED section is the model's free text pasted verbatim, so this run mailed him `gsuite/gsuite/tools/calendar_tools.py:133-134`, an explanation of a 400, *"Say the word and I'll patch it"*, and an offer to write to `~/projects/gsuite/TODO.md`. Harmless for Joshua, fatal for Cody — it reads like an internal dev log. Fix: have `create_items()` return **structured** per-item results (title · date · type · guests · ok/error) and render that section in the app; keep the model's prose in a debug log only.
- [x] **Guests on a task: use `notes`, not the title.**
      **DONE 2026-07-27** — `_gather_items` emits `notes: "With: <names>"` for tasks and
      leaves the title clean; events still get real attendees. Covered by
      `test_row_render.py::test_guests_on_a_task_go_to_notes_not_the_title`.
      `added 2026-07-25`. **Approved 2026-07-25.** `_gather_items` (`gui/app.py:712-718`) folds guest names into the title because Tasks has no attendee field — and since a typed address's "name" *is* the address, live tasks now read `…4 business (w/ jaded423@gmail.com)`. `tasks_create` accepts `notes` (`gsuite/gsuite/tools/tasks_tools.py:147`) — put them there and show the display name, not the raw address. Rarer once event-default lands, but not gone (dateless items).
- [x] **Default the "email the transcript" tick to ON.**
      **DONE 2026-07-27** — `email_on_create` now `BooleanVar(value=True)` (`gui/app.py`).
      The blank-`point4.me.email` item below is now reachable on every run — do it next.
      `added 2026-07-25`. Joshua's call, 2026-07-25: *"default the 'send attached email' tick to be set, and if someone doesn't want it, they can untick."* Opt-out, not opt-in — the audit email is the only artifact that survives a wrong extraction (it carries the transcript *and* the skipped rows Calendar can never tell you about), so the safe state is the default state. Set the checkbox's initial value on the review screen; the address already defaults to the account's own. Worth pairing with the blank-`point4.me.email` item above, since an always-on tick makes a blank target reachable on every run.
- [ ] **Verify only ONE send path survives.** `added 2026-07-25`. **Joshua re-tests 2026-07-26.** The 07-24 fix collapsed "Send now" + create-with-box into a single send, but joshua@elevatedtrading.com holds **two identical** `Meeting transcript — pz79GtYNQsEcyxxanvBaAXuxX1rQNRHD` messages 59 s apart (00:56:38Z / 00:57:37Z) — far too close to be two transcribe runs. Either the double-send is still reachable or a retry re-fired.
      verify: one message per recording id in `gmail_search_messages "subject:'Meeting transcript' newer_than:1d"`
- [x] **↗ Pointer — all-day events + invite defaults are gsuite-owned.** `added 2026-07-25`.
      **CLEARED 2026-07-25 — both gsuite items shipped + live-verified**, so event-default is
      unblocked. `calendar_create_event` now takes `2026-07-28` (all-day) or `2026-07-28T09:00`
      (timed, stamped `America/Chicago` from the calendar itself); `end` is optional — omit it
      and a timed event runs `duration_minutes`, default 30, which is exactly the 9:00–9:30 the
      dropdown wants. Attendees are emailed unless `send_updates='none'` is passed explicitly,
      so the invite no longer depends on the model remembering a prompt sentence.
      The app needs no restart chore (fresh `claude -p` per run); only long-lived sessions
      hold the stale module. Detail:
      [`gsuite/docs/changelog.md`](~/projects/gsuite/docs/changelog.md) 2026-07-25.

      *(original watch note)* Authored in [`~/projects/gsuite/TODO.md`](~/projects/gsuite/TODO.md), watched here because event-default (above) is blocked on the first: (1) `calendar_create_event` can't emit an all-day `{"date": …}`, so a date-only value 400s — the router improvised a midnight→midnight Central block, giving a 24-hour busy bar + hardcoded America/Chicago; (2) `send_updates` defaults to `"none"`, so "attendees attached, nobody notified" stays reachable — it only worked this run because the model remembered a prompt sentence.
- [x] **Clean up the items the wrong-account bug put on jaded423.** `added 2026-07-27`.
      **DONE 2026-07-27** — 8 app-created items removed from jaded423: 3 events (deleted with
      `send_updates='all'`, so the invitee copies cleared from brown.joshua.david automatically)
      + 5 tasks. Verified 0 app-created events and 0 stray tasks on **both** jaded and brown;
      Joshua's own "dishwasher" task left untouched. Scope was larger than first thought — the
      **2026-07-25 run had gone to jaded too** (4 tasks still in the old `(w/ …)` title format,
      plus a `00:00` event that was the old midnight→midnight all-day workaround). So the
      "Create verified live 2026-07-25" note on the shakeout item was real but verified against
      the wrong calendar, which is why nothing looked wrong at the time.

- [ ] **Diarize progress pins at 100%% / ETA 0:00 while it's still working.** `added 2026-07-27`.
      Found by Joshua mid-test: STEP 3 of 6 "Diarizing (embeddings)" sat at `100%% · ETA 0:00`
      for ~5 min (elapsed 5:47, total 10:50) before moving on — it read as hung, and he nearly
      killed a healthy run. It was fine: ~30%% CPU throughout, RSS climbing, and it reached
      step 6 on its own. Cause: a sub-phase after the last line that emits a percentage, so the
      bar saturates and the ETA floors while real work continues. Fix options: hold the bar
      short of 100%% until the stage genuinely ends, switch to indeterminate once the parsed
      percentage tops out, or say what it's doing ("clustering speakers — no progress
      available"). Cody will hit this on a slower Mac harder than Joshua does, and "looks
      hung" is the failure that makes someone force-quit and lose the run.
      resume: **Code DONE 2026-07-28, 104 tests pass** (6 new — `tests/test_diar_progress.py`).
      Took fix options (b)+(c) together, in `trans_runner._emit_transd_progress`: at `(100%)`
      the mapper now emits `frac=None` instead of `1.0`, so the GUI flips to the marquee bar
      and drops the ETA, plus a label naming the silent sub-phase (`_DIAR_NEXT`:
      segmentation→"building embeddings", embeddings→"clustering speakers", unknown→
      "finishing"). Chose the suffix form because `app.py:471` `_phase_key` matches the
      *unclosed* prefix `"Diarizing (embeddings"` — so "STEP n OF m" still resolves to the
      same step; a test pins that contract, since relabelling a phase is exactly what would
      silently mis-number the counter later. **Still open: one live diarized run.** Unit tests
      prove the mapper, not pyannote — the assumption inherited from Joshua's observation is
      that `(100%)` is the *last* line before the silence. If a different silent gap exists
      (e.g. before segmentation starts), it'll still read as stalled, just without the false
      100%. ⚠ A running app holds the old code — quit and relaunch before testing.

- [ ] **Demote the `meeting` MCP in docs.** `added 2026-07-20`. Partial 2026-07-23 (meeting `CLAUDE.md` now leads with the app). Left: the global routing-map line in `~/.claude/CLAUDE.md` still calls meeting an MCP — update on a /sum pass.

## OAuth distribution follow-ups

- [ ] **🔑 #2 — Internal-split OAuth fix (Point4 side still open).** `added 2026-07-17`. Plan: [`~/.claude/plans/gsuite-oauth-internal-split.md`](~/.claude/plans/gsuite-oauth-internal-split.md). Internal apps are CASA-exempt even with restricted Gmail scopes, so the fix is Internal clients (full scope) for Elevated+Point4. Public kit is safe because Internal rejects non-org accounts. **Elevated done 2026-07-20**; next action = verify Cody's org account + Point4 Workspace, then cut the Point4 Internal client.
- [ ] **⚠️ #3 — Reproducibility: the shipped zip was a one-off from local state.** `added 2026-07-17`. `meeting-kit.zip` was built by `build_kit.sh` from Joshua's **local working tree** (uncommitted `kit/`, README edits) — the public repos are stale, so **nobody could regenerate the release from public source.** Correct order when resumed: (a) commit + push all `meeting`+`gsuite` source; (b) rebuild the zip from a **fresh clone** (proves reproducibility); (c) replace the release asset. Caveat: `oauth-client.json` comes from local `~/.config/` (not any repo, correctly) → clean-clone build needs the client supplied separately — which #2 makes clean. *(Superseded by the standalone-app pivot if PyInstaller packaging replaces the kit entirely — re-scope when the Package item lands.)*

## Deferred

- [ ] **Distribute to Cody (BLOCKED on Cody).** `added 2026-07-08`. Needs his Mac specs (M-series? RAM) + Plaud-device-vs-audio-file capture answer.
- [ ] Bring `meeting` MCP to the Pocket: resurrect diarization natively — second venv with pyannote.audio (speaker-diarization-3.1, gated → `~/.secrets/hf_token`) + CPU torch, whisper side = `~/.venvs/whisper` (faster-whisper, 12x realtime on distil per the 2026-09-19 bench), port `transd`'s align step. Test on a recorded meeting, not a sermon. Background: `~/projects/pocket/docs/local-ai.md`. (added 2026-09-19)
