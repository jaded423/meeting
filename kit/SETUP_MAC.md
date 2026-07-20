# meeting kit — fresh-Mac setup

Turns a meeting (audio file, video, or a URL) into **Google Calendar events + Tasks**,
right inside **Claude Desktop**. This kit takes a brand-new Mac from nothing to running.

## The ONE thing you need first
**An Apple-Silicon Mac (M-series).** The transcription engine (`mlx-whisper`) has no Intel
build. That's it — **everything else, including Claude Desktop itself, is installed for you**
(Homebrew, ffmpeg, the Whisper engine, the MCP servers, Claude Desktop).

## Install
1. **Download `meeting-kit.zip`** from the GitHub release (no `git` required).
   *(Why ZIP, not `git clone`? A fresh Mac has no `git` until Command Line Tools exist — a
   chicken-and-egg. The ZIP sidesteps it: you never need `git` to get the installer.)*
2. **Unzip it**, open the folder.
3. *(optional)* Double-click **`check_prereqs.command`** — read-only status.
   *(First time: macOS may say "unidentified developer." Right-click → Open → Open.)*
4. Double-click **`install.command`** — the wizard. If it asks for Command Line Tools, let
   that finish, then double-click `install.command` **again**. It may ask for your Mac
   password (to install Claude Desktop).
5. When a **browser opens**, sign into the Google account for this Mac and grant access.
   The token is saved **on this Mac only**.
6. The wizard runs a **self-test** and tells you if everything works.
7. **Quit and reopen Claude Desktop.**

Re-running `install.command` is always safe — every step checks before it installs, so
nothing is duplicated.

## Use it
In a Claude Desktop chat:
- `/meeting <path-to-audio-or-video>` — or a meeting URL (Fathom/Loom/YouTube/…)
- or just drop a file in and say *"transcribe this and add the action items to my calendar."*

Claude transcribes → pulls out the agreed action items → creates **dated items as Calendar
events** and **open-ended ones as Tasks**. It asks before writing anything.

## Notes
- **Browser:** OAuth opens your **default** browser (Safari is fine). You do **not** need
  Chrome, and you don't need to pre-log-into Google — the sign-in page handles that.
- **Nothing is uploaded.** Transcription runs locally (offline Whisper). The only network
  calls are Google's, for the calendar/task writes you approve.
- **The OAuth client file** bundled here is Google's *installed-app* client — by design it
  is not a confidential secret and does not rotate. Your personal **token** is created
  locally during sign-in and is never part of this kit.
- **Speaker labels (optional):** the default engine is fast and unlabeled. Diarization
  (`transd`) needs extra setup (a HuggingFace token + model access) — skip unless you need
  who-said-what.
- **Re-running `install.command`** is safe; it just refreshes everything.
