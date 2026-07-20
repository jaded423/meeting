"""User-editable settings for meeting.

Lives at ~/.config/meeting/settings.json (override the dir with MEETING_CONFIG_DIR,
mirroring gsuite's GSUITE_CONFIG_DIR). All keys are optional — missing file or
missing key falls back to DEFAULTS. `meeting_status` reads these back with
flip-instructions so Cody can see and change them without reading code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# key -> (default, human note shown by `meeting_status`)
DEFAULTS: dict[str, object] = {
    # Fast trans/small by default; true = transd/large-v3 speaker labels (~10x slower).
    "diarize_default": False,
    # /meeting lists proposed events/tasks and waits for approval before any gsuite write.
    "approval_gate": True,
    # Whisper model for the non-diarized engine.
    "default_model": "small",
    # "" = ~/projects/trans/transcriptions/ (the trans_runner default).
    "output_dir": "",
}


@dataclass(frozen=True)
class Settings:
    diarize_default: bool
    approval_gate: bool
    default_model: str
    output_dir: str


def config_dir() -> Path:
    env = os.environ.get("MEETING_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".config" / "meeting"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> Settings:
    data = dict(DEFAULTS)
    p = settings_path()
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            data.update({k: v for k, v in raw.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass  # malformed file → fall back to defaults, never crash the server
    return Settings(**data)  # type: ignore[arg-type]


def write_default_settings(force: bool = False) -> Path:
    """Write a default settings.json (install.sh calls this so Cody has a file to edit)."""
    p = settings_path()
    if p.is_file() and not force:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(DEFAULTS, indent=2) + "\n", encoding="utf-8")
    return p


# how-to-flip text, `.format(path=...)`-ed by meeting_status
FLIP_HELP: dict[str, str] = {
    "diarize_default": (
        "Speaker labels are OFF by default (fast trans/small engine). To make them ON by "
        'default (transd/large-v3 — labels who said what, ~10x slower), set '
        '"diarize_default": true in {path}. Per-call override: pass diarize to meeting_transcribe.'
    ),
    "approval_gate": (
        "Approval is REQUIRED before /meeting writes to Calendar/Tasks (it lists items and "
        'waits for your OK). To let it write automatically without asking, set '
        '"approval_gate": false in {path}.'
    ),
}
