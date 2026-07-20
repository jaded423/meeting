# meeting — turn a recording into calendar events & tasks

A [MCP](https://modelcontextprotocol.io) server that transcribes a meeting — an audio file, a
video, or a URL — **on your own machine**, then hands the transcript to Claude so it can pull
out the action items and (with the companion [`gsuite`](https://github.com/jaded423/gsuite)
server) drop them straight into **Google Calendar and Tasks**.

Give it a recording in Claude Desktop and get back: dated commitments as **calendar events**,
open-ended to-dos as **tasks** — nothing you didn't agree to, and nothing sent to a cloud
transcription service.

## How it works

Three clean layers, each doing one job:

1. **`meeting` transcribes** — audio/video/URL → text, locally, using Whisper on Apple Silicon
   (fast, offline, free). This server does *only* this.
2. **Claude extracts** — reads the transcript and decides what's actually an action item, who
   owns it, and whether it has a date.
3. **`gsuite` routes** — creates the calendar events (dated) and tasks (undated) in your Google
   account, asking before it writes.

## Install

**On a fresh Apple-Silicon Mac** — the one-click kit installs everything (Homebrew, the Whisper
engine, Claude Desktop, and both MCP servers), then self-tests:

1. Download `meeting-kit.zip` from the [latest release](https://github.com/jaded423/meeting/releases).
2. Unzip it and double-click **`install.command`**.
3. Sign into Google when the browser opens. Reopen Claude Desktop.

See [`kit/SETUP_MAC.md`](kit/SETUP_MAC.md) for the walkthrough.

**From source** (if you already have the `trans` stack — `mlx-whisper` + `ffmpeg`, plus the
`trans`/`transd` scripts on your `PATH` — on your machine):

```bash
git clone https://github.com/jaded423/meeting.git
cd meeting && ./install.sh
```

## Use it

In Claude Desktop:

```
/meeting ~/Recordings/team-sync.m4a
```

…or a URL (Fathom / Loom / YouTube / …), or just drop a file in and say *"transcribe this and
add the action items to my calendar."* Claude transcribes, shows you the items it found, and —
once you approve — creates the events and tasks.

## Tools

| Tool | What it does |
|---|---|
| `meeting.transcribe` | audio/video file · URL · or a text transcript → clean transcript text + files. `diarize` switches to the speaker-labeled engine. |
| `meeting.status` | checks the engine is reachable and shows current settings. Run it first if transcription fails. |
| `/meeting <input>` | the full flow: transcribe → extract action items → create calendar events + tasks (via `gsuite`). |

## Requirements

- **Apple-Silicon Mac (M-series).** The Whisper engine (`mlx-whisper`) has no Intel build.
- **Claude Desktop** (installed for you by the kit) and the
  [`gsuite`](https://github.com/jaded423/gsuite) server for the calendar/task routing.

## Privacy

Transcription runs **entirely on your machine** — audio never leaves it. The only network
calls are Google's, for the calendar and task writes you approve.

## Notes

- **Speaker labels** are optional: the default engine is fast and unlabeled. Diarization
  (who-said-what) needs a HuggingFace token and model access — enable it per call with
  `diarize: true`.
- **Settings** live in `~/.config/meeting/settings.json` (default engine, an approval gate,
  output folder); see them with `meeting.status`.

## Development

Server code is in `meeting/`; tests in `tests/` (`pytest`). It shells out to the local
`trans`/`transd` scripts — it owns no transcription logic of its own. Design notes and history
are in [`docs/`](docs/).
