"""Meeting Assistant — standalone local app.

The muscle: takes a text / audio / URL input, does the heavy transcription
locally (progress bar + ETA), then relays the finished transcript to the
headless-Claude brain (`claude -p`, subscription auth) which extracts action
items and routes them to Google Calendar / Tasks via the gsuite MCP.

Shape mirrors two things Joshua already built: photoEditor (local media
grunt-work) + the `todo()` shell wrapper (a dumb relay to a headless `claude`).
The app holds no meeting intelligence — it transcribes and relays.
"""

from __future__ import annotations

__all__ = ["transcribe", "brain", "cli"]
