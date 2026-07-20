"""meeting_status — diagnostic + settings readout.

Lets Cody (or Joshua) self-check a broken install and see the current settings
with flip-instructions, without shell access or reading code.
"""

from __future__ import annotations

import shutil
from typing import Any

from .. import settings as _settings
from .. import trans_runner
from ._registry import tool

# The augmented PATH the transcription subprocess would actually run under — probe
# against it, not the server's bare PATH, or mlx_whisper/yt-dlp read as missing.
_ENV_PATH = trans_runner._augmented_env()["PATH"]


def _which(name: str) -> dict[str, Any]:
    path = shutil.which(name, path=_ENV_PATH)
    return {"available": path is not None, "path": path}


def _probe_script(name: str) -> dict[str, Any]:
    try:
        return {"available": True, "path": trans_runner._resolve_bin(name)}
    except trans_runner.TransError:
        return {"available": False, "path": None}


@tool(
    name="meeting_status",
    description=(
        "Diagnostic + settings readout for the meeting MCP. Reports whether the local trans "
        "stack (trans / transd / mlx_whisper / yt-dlp) is reachable, and the current settings "
        "(diarize_default, approval_gate, model, output dir) with instructions for changing "
        "each. Call this first when transcription fails or to check defaults."
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
def status() -> dict[str, Any]:
    cfg = _settings.load_settings()
    sp = str(_settings.settings_path())

    engines = {
        "trans": _probe_script("trans"),
        "transd": _probe_script("transd"),
        "mlx_whisper": _which("mlx_whisper"),
        "yt_dlp": _which("yt-dlp"),
    }
    # The fast path needs trans + mlx_whisper; URL input also needs yt-dlp; diarize needs transd.
    ready = engines["trans"]["available"] and engines["mlx_whisper"]["available"]

    return {
        "ok": True,
        "ready": ready,
        "engines": engines,
        "settings": {
            "diarize_default": cfg.diarize_default,
            "approval_gate": cfg.approval_gate,
            "default_model": cfg.default_model,
            "output_dir": cfg.output_dir or str(trans_runner.DEFAULT_OUTPUT_DIR),
            "config_file": sp,
        },
        "how_to_change": {
            "diarize_default": _settings.FLIP_HELP["diarize_default"].format(path=sp),
            "approval_gate": _settings.FLIP_HELP["approval_gate"].format(path=sp),
        },
    }
