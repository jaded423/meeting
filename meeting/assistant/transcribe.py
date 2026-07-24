"""Progress-aware transcription for the Meeting Assistant.

Drives `mlx_whisper` directly (not the `trans` wrapper) so we can:
  (a) render a live progress bar + ETA off the segment timestamps it prints, and
  (b) pass the anti-hallucination decode flags that stop Whisper's "Okay. Okay."
      repeat-loops on silence (the 30-min glitch from the first real test).

Text inputs (a prior transcript) and diarized runs fall back to the shared
`trans_runner` (passthrough / `transd`). URLs are pulled with yt-dlp first.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .. import trans_runner

HOME = Path.home()
_VOCAB = HOME / "projects" / "trans" / "vocab.txt"
_FORMATS = ("txt", "srt", "vtt", "tsv", "json")
_TEXT_EXT = trans_runner._TEXT_EXT  # reuse the passthrough set
# whisper prints "[00:00.000 --> 00:05.000]  text"; grab the end timestamp.
_TS = re.compile(r"-->\s*(\d+:\d+(?::\d+)?\.\d+)\]")
# yt-dlp (with --newline) prints "[download]  42.3% of ...".
_YT_PCT = re.compile(r"\[download\]\s+([\d.]+)%")

# Anti-hallucination decode flags (the "Okay. Okay." fix). condition-on-previous
# =False stops it feeding a hallucinated loop back into itself; the silence
# threshold skips dead air rather than inventing filler for it.
_ANTI_HALLUCINATION = [
    "--condition-on-previous-text", "False",
    "--hallucination-silence-threshold", "2.0",
    "--compression-ratio-threshold", "2.4",
    "--logprob-threshold", "-1.0",
    "--no-speech-threshold", "0.6",
]

ProgressFn = Callable[[str, "float | None"], None]  # (phase_label, fraction 0..1 or None)


class TranscribeError(RuntimeError):
    pass


class TranscribeCancelled(TranscribeError):
    """Raised when a `stop_event` was set mid-run — user pressed Cancel."""


def _mlx_whisper_bin() -> str:
    return shutil.which("mlx_whisper") or str(HOME / ".venvs" / "diarize" / "bin" / "mlx_whisper")


def _yt_dlp_bin() -> str:
    return shutil.which("yt-dlp") or str(HOME / ".local" / "bin" / "yt-dlp")


def _duration(path: str) -> float | None:
    """Media length in seconds via ffprobe (drives the ETA); None if unknown."""
    ff = shutil.which("ffprobe")
    if not ff:
        return None
    try:
        out = subprocess.run(
            [ff, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return None


def _parse_ts(s: str) -> float:
    parts = [float(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, sec = parts
    return h * 3600 + m * 60 + sec


def _download(url: str, name: str, tmp_dir: Path,
              on_progress: ProgressFn | None = None) -> Path:
    out = tmp_dir / f"{name}.m4a"
    # --newline makes yt-dlp emit progress on fresh lines (not \r) so we can stream %.
    cmd = [_yt_dlp_bin(), "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
           "-o", str(out), "--no-warnings", "--newline", "--progress", url]
    try:
        proc = subprocess.Popen(
            cmd, env=trans_runner._augmented_env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except OSError as exc:
        raise TranscribeError(f"yt-dlp download failed: {exc}") from exc
    assert proc.stdout is not None
    if on_progress:
        on_progress("Downloading audio", None)
    for line in proc.stdout:
        m = _YT_PCT.search(line)
        if m and on_progress:
            try:
                on_progress("Downloading audio", float(m.group(1)) / 100.0)
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0 or not out.is_file():
        raise TranscribeError(f"yt-dlp download failed (exit {proc.returncode}) for {url}")
    return out


def _collect(out_dir: Path, name: str) -> dict[str, str]:
    return {
        ext: str(out_dir / f"{name}.{ext}")
        for ext in _FORMATS
        if (out_dir / f"{name}.{ext}").is_file()
    }


def transcribe(
    input_str: str,
    *,
    name: str,
    out_dir: Path,
    model: str = "small",
    diarize: bool = False,
    on_progress: ProgressFn | None = None,
    stop_event: Any = None,
) -> dict[str, Any]:
    """Transcribe `input_str` → {engine, name, output_dir, text, files, seconds}.

    - text file  → passthrough (trans_runner), instant.
    - diarize    → transd via trans_runner (speaker labels; no fine-grained bar).
    - audio/URL  → mlx_whisper here, with progress callbacks + anti-hallucination.

    `stop_event` (anything with `.is_set()`, e.g. a `threading.Event`) lets a GUI
    cancel a running whisper transcription — checked between output segments; when
    set, the subprocess is terminated and `TranscribeCancelled` is raised. The text
    and diarize paths are quick / not-yet-interruptible, so cancel there is best-effort.
    """
    def _cancelled() -> bool:
        return stop_event is not None and stop_event.is_set()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    in_path = Path(input_str).expanduser()

    # 1. Already-text input → passthrough (no ASR).
    if in_path.is_file() and in_path.suffix.lower() in _TEXT_EXT:
        r = trans_runner.run(str(in_path), name=name, output_dir=str(out_dir))
        r["seconds"] = time.time() - started
        return r

    # 2. Diarized → hand to transd (speaker labels for "who said what"). transd
    #    streams its own stage/turn progress, which trans_runner forwards.
    if diarize:
        r = trans_runner.run(input_str, name=name, diarize=True,
                             output_dir=str(out_dir), model=model,
                             on_progress=on_progress, stop_event=stop_event)
        r["seconds"] = time.time() - started
        return r

    # 3. Audio / URL → mlx_whisper here, with our own progress + flags.
    with tempfile.TemporaryDirectory(prefix="meeting-asst-") as td:
        tmp = Path(td)
        if in_path.is_file():
            audio = str(in_path)
        elif "://" in input_str:
            audio = str(_download(input_str, name, tmp, on_progress))
        else:
            raise TranscribeError(f"input not found and not a URL: {input_str}")

        if _cancelled():
            raise TranscribeCancelled("cancelled before transcription started")

        total = _duration(audio)
        cmd = [
            *trans_runner._arm64_prefix(), _mlx_whisper_bin(), audio,
            "--model", f"mlx-community/whisper-{model}-mlx",
            "--output-format", "all",
            "--output-name", name,
            "--output-dir", str(out_dir),
            "--verbose", "True",
            *_ANTI_HALLUCINATION,
        ]
        if _VOCAB.is_file():
            vocab = _VOCAB.read_text(encoding="utf-8", errors="replace").strip()
            if vocab:
                cmd += ["--initial-prompt", vocab]

        # PYTHONUNBUFFERED=1 is load-bearing: without it mlx_whisper block-buffers
        # its stdout when piped, so the segment lines (and thus the progress bar)
        # don't arrive until the very end. With it, they stream live.
        env = trans_runner._augmented_env()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = subprocess.Popen(
                cmd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except OSError as exc:
            raise TranscribeError(f"failed to launch mlx_whisper: {exc}") from exc

        assert proc.stdout is not None
        if on_progress:
            on_progress("Transcribing", None)  # model-load / first-segment wait
        tail_lines: list[str] = []
        for line in proc.stdout:
            tail_lines.append(line)
            if len(tail_lines) > 40:  # keep only the last lines for error context
                tail_lines.pop(0)
            if _cancelled():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise TranscribeCancelled("transcription cancelled by user")
            m = _TS.search(line)
            if m and on_progress:
                frac = min(1.0, _parse_ts(m.group(1)) / total) if total else None
                on_progress("Transcribing", frac)
        proc.wait()

    txt = out_dir / f"{name}.txt"
    if proc.returncode != 0 or not txt.is_file():
        tail = "".join(tail_lines).strip()[-800:]
        raise TranscribeError(
            f"mlx_whisper failed (exit {proc.returncode}); no transcript at {txt}."
            + (f"\nOutput tail:\n{tail}" if tail else "")
        )
    return {
        "engine": f"mlx_whisper:{model}",
        "name": name,
        "output_dir": str(out_dir),
        "text": txt.read_text(encoding="utf-8", errors="replace"),
        "files": _collect(out_dir, name),
        "seconds": time.time() - started,
    }
