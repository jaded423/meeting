"""meeting_transcribe — audio/URL/file → transcript, via the local trans stack."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import settings as _settings
from .. import trans_runner
from . import _errors
from ._registry import tool

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "description": (
                "A yt-dlp URL (YouTube / Loom / Fathom share link / etc.) OR an "
                "absolute path to a local audio/video file (mp3/m4a/wav/mp4/mov)."
            ),
        },
        "diarize": {
            "type": "boolean",
            "description": (
                "Label speakers using the diarized large-v3 engine (transd). Slower. "
                "Omit to use the diarize_default setting (default false = fast mlx small "
                "via trans); pass true/false to override for this call."
            ),
        },
        "model": {
            "type": "string",
            "description": (
                "Whisper model for the non-diarized engine (e.g. 'base', 'small', "
                "'large-v3'). Ignored when diarize=true. Omit to use the default_model setting."
            ),
        },
        "name": {
            "type": "string",
            "description": "Output basename (no extension). Defaults to the file stem or a URL slug.",
        },
        "output_dir": {
            "type": "string",
            "description": "Where to write transcripts. Default ~/projects/trans/transcriptions/.",
        },
        "include": {
            "type": "array",
            "items": {"type": "string", "enum": ["srt", "vtt", "tsv", "json"]},
            "description": (
                "Extra timestamped formats to inline in the response (file contents). "
                "Clean text is always returned. Default none."
            ),
        },
        "timeout": {
            "type": "integer",
            "description": "Max seconds to wait for transcription. Default 3600.",
        },
    },
    "required": ["input"],
    "additionalProperties": False,
}


@tool(
    name="meeting_transcribe",
    description=(
        "Transcribe a meeting/audio/video source (URL or local file) to text using the "
        "local trans stack (Whisper on Apple Silicon; free, offline). Returns clean "
        "transcript text plus the paths of the written files, with optional speaker "
        "diarization. This is layer 2 (transcribe) of the meeting pipeline — you (the host "
        "Claude) do the extraction (action items / SOP) and gsuite routes to Calendar/Tasks."
    ),
    input_schema=_SCHEMA,
)
def transcribe(
    *,
    input: str,
    diarize: bool | None = None,
    model: str | None = None,
    name: str | None = None,
    output_dir: str | None = None,
    include: list[str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    input_str = (input or "").strip()
    if not input_str:
        return _errors.error("input is required (a URL or a local file path)")

    is_url = "://" in input_str
    if not is_url:
        local = Path(input_str).expanduser()
        if not local.exists():
            return _errors.error(
                f"local file not found: {input_str}",
                hint="pass an absolute path, or a URL for remote sources",
            )
        input_str = local.as_posix()

    # Args override settings; omitted args fall back to the user's settings.json.
    cfg = _settings.load_settings()
    use_diarize = cfg.diarize_default if diarize is None else bool(diarize)
    use_model = None if use_diarize else (model or cfg.default_model)
    use_output_dir = output_dir or (cfg.output_dir or None)

    try:
        result = trans_runner.run(
            input_str,
            name=name,
            diarize=use_diarize,
            model=use_model,
            output_dir=use_output_dir,
            timeout=timeout,
        )
    except trans_runner.TransError as exc:
        return _errors.error(str(exc), retryable=True)

    payload: dict[str, Any] = {"ok": True, **result}
    if include:
        want = set(include)
        extra: dict[str, str] = {}
        for ext, path in result["files"].items():
            if ext in want:
                try:
                    extra[ext] = Path(path).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
        if extra:
            payload["extra"] = extra
    return payload
