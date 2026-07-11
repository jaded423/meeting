"""meeting — transcription MCP server.

Packages the local `trans` stack (Whisper on Apple Silicon) as Claude-usable
tools. Layer 2 (transcribe) of the meeting pipeline; the host Claude does
extraction (action items / SOP) and gsuite routes to Calendar/Tasks.
"""

__version__ = "0.1.0"
