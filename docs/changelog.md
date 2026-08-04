---
type: log
title: meeting — changelog
tags: [meeting, changelog]
related: [index]
---

# meeting — Changelog

Append-only. Newest on top. Written by `/log`.

## 2026-07-28 — The app had never actually been launched the way users launch it

**Three fixes, two of them the same root cause.** Joshua double-clicked
`MeetingAssistant.app` for the first time (previous runs were all started from a terminal)
and it failed immediately. A GUI started by **LaunchServices — double-click *and* `open`,
both** — inherits launchd's environment, not a shell's: minimal
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, and none of the exports from `~/.zshrc.local`.

**What changed:**
- **`trans_runner.ensure_path()`** — repairs the interpreter's own `PATH` from the existing
  `_PATH_EXTRA`, called first thing in `gui/app.py:main()`. Without it `claude`
  (`~/.local/bin`) was invisible, so `brain.auth_status()` got `FileNotFoundError` and the app
  reported *"Claude Code isn't installed on this Mac"* on a Mac where it is. `ffprobe` (drives
  the ETA) was equally invisible. Deliberately **not** a new directory list — `_PATH_EXTRA` +
  `_augmented_env()` already held the right dirs and were only ever applied to *child*
  processes; this points the same knowledge at the parent.
- **`trans_runner.hf_token()`** — env → `~/.secrets/hf_token` → `~/.cache/huggingface/token`
  (the `huggingface-cli login` location), injected in `_augmented_env()`. `HF_TOKEN` was a
  shell export, so under a Finder launch `transd` exited 1 with *"HF_TOKEN required"* and the
  gated pyannote models were unreachable.
- **Diarize pre-flight + ANSI stripping** — diarizing with no token now raises an actionable
  `TransError` *before* launching transd, instead of exiting 1 thirty seconds later; and the
  error tail is ANSI-stripped, because transd's colour codes were reaching the GUI dialog as
  literal `[0;31m`.
- **Diarize progress no longer pins at 100% / ETA 0:00** — at `(100%)` the mapper emits
  `frac=None` instead of `1.0`, so the GUI takes its existing indeterminate branch (marquee,
  no ETA) and labels the silent sub-phase via `_DIAR_NEXT` (segmentation→"building
  embeddings", embeddings→"clustering speakers"). pyannote's counter tops out and then runs
  ~5 min of speaker clustering emitting nothing; the bar saturating made a healthy run read as
  hung and Joshua nearly killed one.

**Why:**
- Every prior "verified live" run was terminal-launched, so the app had **never** been
  exercised in the configuration it ships in. Both env bugs were invisible for that reason
  alone — the same shape as the 2026-07-27 wrong-account bug, where every success signal was
  real but pointed somewhere unintended.

**Files modified:**
- `meeting/trans_runner.py` — `ensure_path()`, `hf_token()`, `_HF_TOKEN_FILES`, `_DIAR_NEXT`,
  `_ANSI`, diarize pre-flight in `run()`, `_emit_transd_progress()` 100% branch
- `meeting/assistant/gui/app.py` — `trans_runner.ensure_path()` at the top of `main()`
- `tests/test_diar_progress.py` — new; 11 tests (87 → 110 suite-wide with the day's other work)

**Technical notes:**
- The phase label is a **contract** with `app.py:_phase_key()`, which resolves "STEP n OF m" by
  prefix-matching the *unclosed* `"Diarizing (embeddings"`. The 100% relabel is a suffix
  specifically so that match survives; a test pins it, since relabelling a phase is exactly
  what would silently mis-number the step counter later.
- **Testing trap, do not "fix":** the Claude CLI's keychain lookup keys on **`$USER`**. Strip
  it (as `env -i` does) and `claude auth status` reports `loggedIn:false` even with a good
  PATH. A real Finder launch passes `USER`/`HOME`/`LOGNAME` — only `PATH` is minimal.
- Repro for the whole class: `env -i HOME=$HOME USER=$USER PATH=/usr/bin:/bin <cmd>`.
- The gated pyannote models total **31 MB** (the 18 GB HF cache is almost all Whisper), so
  pre-seeding them in the installer + relaxing transd's unconditional `HF_TOKEN` guard to
  "token **or** populated cache" would remove the HF-account requirement for Cody entirely.
  Verified the cached repos resolve with no token via `snapshot_download(local_files_only=True)`.
  Not done — `transd` lives in the `scripts` repo.

---

## 2026-07-27 — The account selector never bound anything (wrong-calendar bug)

**Found by Joshua on the first live run after the event-default change.** A run with
`account: 'elevated'` (confirmed in the app log) emailed the transcript from
joshua@elevatedtrading.com — correct — and created all the calendar events on
**jaded423@gmail.com**. A Point4 meeting landed on a personal calendar next to family
birthdays. The Elevated calendar got nothing. Verified by reading the events back: organizer
and creator are both `jaded423@gmail.com`; `gsuite-elevated` (= joshua@elevatedtrading.com,
1 calendar) has no such event.

**Cause:** `--allowedTools` is a **permission allowlist**, and every brain call runs
`--dangerously-skip-permissions`, which bypasses permission checks entirely. Naming
`mcp__gsuite-elevated__calendar_create_event` therefore bound *nothing*. All four `gsuite-*`
servers in the user's global config were loaded into the `claude -p` session, the model saw
four identical `calendar_create_event` tools, and picked per call — Gmail from one account,
Calendar from another, in the same run. Nothing in the logs flagged it; it reported success.

**Fix:** binding is now structural. `_account_mcp_config()` writes a one-server MCP config for
the selected account and `_bind()` appends `--mcp-config <that> --strict-mcp-config`, so the
other accounts **do not exist** in the session. Applied to all three Google-touching call
sites: `create_items`, `email_transcript`, and `route(do_route=True)`. The `--allowedTools`
lines stay as documentation of intent; they are no longer load-bearing. Verified live: a
`claude -p` run under the new flags enumerates no tools from any other account.

A missing/unregistered server now raises `AccountBindingError` and the call returns
`ok=False` **without running** — a run that cannot prove which account it will write to must
not write. +11 tests (98 total), asserting on the flags, the generated config, and that a
binding failure never reaches `_run`.

**Blast radius was two runs, not one.** Cleanup removed 8 app-created items from jaded423 —
3 events (deleted with `send_updates='all'`, which cleared the invitee copies from
brown.joshua.david automatically) and 5 tasks. Four of those tasks still carried the old
`(w/ …)` title format, i.e. **the 2026-07-25 run had gone to the wrong account too** — so the
"Create verified live 2026-07-25" note was accurate about the mechanics and wrong about the
destination. Nothing reached a third party: every guest address in both runs was one of
Joshua's own accounts. Both accounts verified clean afterwards.

## 2026-07-27 — Events by default, a time picker, and an audit email fit to send

Four changes decided with Joshua on 2026-07-25, all of them downstream of one fact: **Google
Tasks has no attendee field.** A dated deliverable that became a task could never notify
anyone — proved 2026-07-24, when 3 tasks were created, all `Only me`, and nobody was told.

**Events are now the default** (`_PROPOSE_JSON` + `_AUDIT_JSON`, `brain.py`). The old rule was
the inverse: `event` only when a date existed, so anything timeless became a task and lost its
notify path. Now `event` is chosen whenever a date is derivable — with or without a stated
time — and `task` only when there is no date at all. Undated items still list the people in
`participants` and say *"needs a date to invite X"* in `ambiguous`, so the review panel can ask
for the one field that turns it into something people get invited to.

**Time-of-day picker on every event row** (`gui/app.py`). Half-hour slots across the working
day plus an explicit **All day**, defaulting to **9:00 AM** — because a commitment usually
arrives with no stated time, and an all-day event renders as a 24-hour busy bar people scroll
past. `_split_when` / `_join_when` are the whole contract: a bare date means the model heard no
time (→ 9:00, not all-day); the picker emits `YYYY-MM-DD HH:MM` for a slot and `YYYY-MM-DD`
for All day, which is exactly what [gsuite's 2026-07-25 fix](~/projects/gsuite/docs/changelog.md)
turns into a timed or all-day event. **No timezone is sent** — the tool stamps the calendar's
own. The picker greys out on a Task, which stores a date and ignores any time.

**The audit email no longer carries the router's prose.** `create_items()` now returns
structured per-item results — action · date · type · guests · ok/error — and `format_created()`
renders them; the model's free text stays in the log. The 2026-07-25 email had pasted a source
path with line numbers, an explanation of a 400, *"Say the word and I'll patch it"* and an offer
to write to a TODO file into Joshua's inbox. Harmless for him, unusable for Cody. A failed item
now reports as `✗ NOT created — <action> · <why>` instead of vanishing.

**Guests on a task go to `notes`, not the title.** `tasks_create` accepts `notes`; folding names
into the title had produced live tasks reading `…4 business (w/ jaded423@gmail.com)`, because a
typed address is its own display name. Events are unaffected — guests become real attendees.

**The transcript email defaults to ON.** Opt-out, not opt-in: it is the only artifact that
survives a wrong extraction, since it carries both the transcript and the rows that were
*skipped* — the half Calendar can never tell you about.

+33 tests (picker round-trip, CREATED rendering, `create_items` contract, and a real-Tk render
smoke test that drives the row wiring), **87 pass**.

**Not yet proven:** the prompt half. Whether the model actually prefers `event` under the new
rule can only be confirmed by a live run — the mechanical half is covered by tests.

## 2026-07-24 — Claude sign-in made self-service (`auth.command`)

Distribution prep. The brain runs on the user's **Claude subscription** (`_run()` blanks
`ANTHROPIC_API_KEY`, so it always resolves that way — no API key, no config). That sign-in
lapses periodically, and until now every brain call then failed with *"The brain (claude -p)
failed — see logs"* — meaningless to a non-technical user, and a support call every time.

**What changed:**
- **`brain.auth_status()`** — reads `claude auth status --json` (`loggedIn` / `authMethod`).
  Distinguishes *signed out* from *Claude Code not installed*, since the fix differs.
- **Pre-flight in `TranscribeWorker`** — checked **before** transcription starts. Previously a
  lapsed sign-in was only discovered after a 20-minute transcribe.
- **`brain.ensure_auth_command()`** — generates `~/.config/meeting-assistant/auth.command`, a
  double-clickable macOS helper that opens Terminal → `claude auth login` → verifies → reports.
  **Generated, not shipped**: one source of truth, no packaging path to get wrong, self-heals if
  edited or deleted. It re-adds `/opt/homebrew/bin` etc. to `PATH` (a double-clicked `.command`
  doesn't inherit the shell profile) and `unset ANTHROPIC_API_KEY` so a stray key can't shadow
  the subscription sign-in.
- **`_prompt_sign_in()`** — a real dialog ("Open the sign-in window now?") that launches it, and
  names the path so it can be run by hand. Not-installed gets the `npm install -g` line instead.
- **`brain.looks_like_auth_failure()`** — backstop for a sign-in that lapses mid-run, after the
  pre-flight passed. Also wired into `CreateWorker`.

**Tests:** +15 (`tests/test_auth.py`), 54 total. One caught a real bug: `os.makedirs` sat
outside the `try` in `ensure_auth_command`, so an unwritable home would have crashed the sign-in
dialog at the exact moment it was needed.

## 2026-07-24 — First live-send shakeout: two bugs fixed

Joshua's first real **Create** attempt surfaced both.

**1. A dateless Event can't be created — now blocked before you can click.**
The brain proposed two items as `type: event` with `date: null` (its rule was "event if it has
a date **OR** involves someone else"). `calendar_create_event` requires start/end, so the router
correctly refused and stopped to ask — but only *after* the confirm dialog, and it had already
been told to invite a real person. Fixed at both ends:
- **Prompt (root cause):** `"type": "event"` now requires a date in both `_PROPOSE_JSON` and
  `_AUDIT_JSON`. An undated item is a `task` even when others are involved — participants are
  still listed, with `ambiguous: "needs a date to invite X"` so a human can supply one.
- **UI (the guard):** `App._row_problem()` + a live `trace_add` on each row's date/type. A
  selected dateless event disables **Create**, flags the date field, and explains in the footer.
- **Tasks keep their people:** Google Tasks has no guest field, so `_gather_items` now appends
  *every* invitee name to a task's title (previously only no-email names on events), instead of
  dropping the guest list silently.

**2. The report could be emailed twice** — "Send now" then Create-with-the-box-ticked sent it
once each. There is now **one send path**: the email rides along with Create. The button
relabels itself for what will actually happen — `Create 3 + email →`, `Create 3 →`,
`Email transcript only →` (nothing selected, box ticked), or a disabled `Nothing selected`.

**Why:** both are the same class of bug — the UI let you reach a state the backend can't honour.

**Tests:** +6 (`tests/test_review_validation.py`), 39 total.

## 2026-07-24 — Completeness safety net (second pass + coverage ledger + audit email)

Answers "did it capture everything?" — the question you cannot answer yourself for a meeting
you did not attend.

**What changed:**
- **`brain.audit_coverage()`** — a second, adversarial `claude -p` pass. It re-reads the
  transcript *knowing what the first pass caught*, is told the first pass under-includes, and
  is instructed to break ties toward "missed" (a false alarm costs one glance; a real miss
  costs a deliverable). Returns a **topic ledger** — every topic tagged `covered` /
  `no-action` / `missed` — plus the missed items in the first pass's own schema. Read-only:
  no write tools granted. Toggle on the setup screen ("Double-check for missed items",
  default ON); adds a 6th pipeline step to the "STEP N OF M" counter.
- **Coverage panel** on the review screen (`gui/app.py`) — `3 speakers · 9 topics · 4 items`
  plus `⚠ N the first pass missed`, with an expandable topic list. Makes under-inclusion
  *visible*: "9 topics → 4 items" is a question you can only ask if you can see both numbers.
- **Second-pass candidates ride in the same list**, always **unchecked** and tagged
  `⊕ 2nd pass` — you opt them in; you never have to spot them.
- **`brain.email_transcript()`** + review-screen controls (checkbox + address, or "Send now")
  — mails the transcript as a **file attachment** with the coverage report as the body. The
  audit ledger records **skipped** rows too, which is the half you cannot reconstruct from
  Calendar afterwards.
- **`_run()` helper** in `brain.py` — the `claude -p` subprocess boilerplate was about to be
  copy-pasted a 4th and 5th time; now one function, five callers.
- **20 tests** (`tests/test_brain_audit.py`), 33 total.

**Why:**
- Joshua, 2026-07-24: a real Luis "four-pillars design" deliverable was dropped on one run,
  and for a meeting he did not attend there is no ground truth to notice it by.

**Gotchas:**
- The transcript is passed to the mailer **by path, never through the model's context** — a
  2-hour transcript would otherwise cost more to mail than to transcribe, and could be
  silently paraphrased on the way out. `Read` is explicitly disallowed on that call so it
  cannot open what it is attaching; a locked test asserts the body never appears in the prompt.
- The audit is **best-effort by construction**: unparseable JSON, a non-zero exit, a timeout or
  a failed launch all yield an empty ledger, never an exception. A broken second pass must
  never cost you the items the first pass *did* find.
- An unrecognised topic status normalises to `missed` — fail toward the human.

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
