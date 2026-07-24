"""Subprocess bridge to the local `trans` / `transd` scripts.

`meeting` owns no transcription logic — it shells out to the same CLI tools
Joshua runs by hand (`~/scripts/bin/trans`, `transd`) and collects their output.
Both share one contract: `<bin> <url|file> [name]`, honor `TRANS_DIR` for the
output directory, and write `<name>.{txt,srt,vtt,tsv,json}`. `.txt` is clean
text; the rest carry timestamps / speaker labels.

MCP servers launch with a minimal PATH, so we augment it with the dirs the trans
stack's runtime deps (mlx_whisper, yt-dlp, the diarize venv) live in — otherwise
`command -v mlx_whisper` inside the script fails.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

HOME = Path.home()
SCRIPTS_BIN = HOME / "scripts" / "bin"
# Default sink doubles as the SOP-authoring handoff dir (step 5): a transcript
# here is what the host Claude reads to author trans/SOPs/<topic>.md.
DEFAULT_OUTPUT_DIR = HOME / "projects" / "trans" / "transcriptions"
_FORMATS = ("txt", "srt", "vtt", "tsv", "json")
# Already-text inputs (a prior transcript, or a meeting note) — no ASR needed,
# just read them through. Lets Cody bootstrap a previously-trans'd meeting.
_TEXT_EXT = {".txt", ".md", ".srt", ".vtt", ".tsv"}
_PATH_EXTRA = [
    str(SCRIPTS_BIN),
    "/opt/homebrew/bin",
    "/usr/local/bin",
    str(HOME / ".local" / "bin"),
    str(HOME / ".venvs" / "diarize" / "bin"),
]
_DEFAULT_TIMEOUT = 3600  # transcription is slow; a 28-min meeting ~= 13 min on large-v3

# transd stage markers we surface as progress phases (see ~/scripts/bin/transd).
_TD_PCT = re.compile(r"\[download\]\s+([\d.]+)%")
_TD_CHUNK = re.compile(r"chunk (\d+)/(\d+)")
# pyannote internal progress, emitted by transd when TRANS_PROGRESS=1:
#   "  [diar] segmentation 12/34 (35%)"
_TD_DIAR = re.compile(r"\[diar\]\s+(\w+)\s+\d+/\d+\s+\((\d+)%\)")

def _detect_apple_silicon() -> bool:
    """True on Apple Silicon hardware — even when the caller runs under Rosetta.

    Computed once at import (before any test mocks `subprocess.Popen`); `sysctl`
    reports the real hardware, unlike `platform.machine()` which lies under Rosetta.
    """
    try:
        out = subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() == "1"
    except (OSError, subprocess.SubprocessError):
        return False


_ARM64_HW = _detect_apple_silicon()


def _arm64_prefix() -> list[str]:
    """`['arch','-arm64']` on Apple Silicon so MLX / pyannote run native.

    MLX is arm64-only: if this process happens to run under x86_64 (a Rosetta
    terminal, or an app bundle launched x86_64), a child mlx_whisper inherits x86_64
    and dies with `incompatible architecture … need 'x86_64'`. Forcing the child to
    arm64 makes transcription work regardless of the parent's architecture.
    """
    return ["arch", "-arm64"] if _ARM64_HW else []


class TransError(RuntimeError):
    """The trans/transd subprocess could not run or produced no transcript."""


def _emit_transd_progress(line: str, on_progress) -> None:
    """Map a transd stdout line to an on_progress(phase, fraction) call."""
    m = _TD_DIAR.search(line)  # real pyannote progress (segmentation / embeddings)
    if m:
        on_progress(f"Diarizing ({m.group(1)})", int(m.group(2)) / 100.0)
        return
    m = _TD_PCT.search(line)
    if m:
        try:
            on_progress("Downloading audio", float(m.group(1)) / 100.0)
        except ValueError:
            pass
        return
    m = _TD_CHUNK.search(line)
    if m:
        i, n = int(m.group(1)), int(m.group(2))
        on_progress(f"Transcribing turn {i}/{n}", (i / n) if n else None)
        return
    low = line.lower()
    if "[1/3]" in line or "downloading audio" in low:
        on_progress("Downloading audio", None)
    elif "diariz" in low and "chunk" not in low:
        on_progress("Diarizing speakers", None)
    elif "[3/3]" in line or "writing" in low and "format" in low:
        on_progress("Writing transcript", None)


def _resolve_bin(name: str) -> str:
    direct = SCRIPTS_BIN / name
    if direct.is_file() and os.access(direct, os.X_OK):
        return str(direct)
    found = shutil.which(name)
    if found:
        return found
    raise TransError(f"{name} not found (looked in {SCRIPTS_BIN} and PATH)")


def _augmented_env() -> dict[str, str]:
    env = dict(os.environ)
    parts = _PATH_EXTRA + env.get("PATH", "").split(os.pathsep)
    seen: set[str] = set()
    ordered: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    env["PATH"] = os.pathsep.join(ordered)
    return env


def _default_name(input_str: str, diarize: bool) -> str:
    p = Path(input_str)
    if p.exists():
        stem = p.stem
    else:  # URL: sanitize a short slug from the tail
        tail = re.sub(r"[^A-Za-z0-9]+", "-", input_str.rsplit("/", 1)[-1]).strip("-")
        stem = tail[:40] or "transcript"
    return f"{stem}-diarized" if diarize else stem


def run(
    input_str: str,
    *,
    name: str | None = None,
    diarize: bool = False,
    model: str | None = None,
    output_dir: str | None = None,
    timeout: int | None = None,
    on_progress=None,
    stop_event=None,
) -> dict[str, Any]:
    """Run trans/transd on `input_str`; return {engine, name, output_dir, text, files}.

    Raises TransError if the binary is missing, times out, or writes no .txt.

    `on_progress(phase, fraction)` (optional) is called as transd streams its
    stages; `stop_event` (anything with `.is_set()`) terminates the run when set.
    Both default to None → original blocking behavior (the MCP path is unaffected).
    """
    # Already-text input (a prior transcript / meeting note) — no ASR, just read it
    # through so Cody can bootstrap a previously-trans'd meeting into the flow.
    in_path = Path(input_str)
    if in_path.is_file() and in_path.suffix.lower() in _TEXT_EXT:
        return {
            "engine": "passthrough",
            "name": name or in_path.stem,
            "output_dir": str(in_path.parent),
            "text": in_path.read_text(encoding="utf-8", errors="replace"),
            "files": {in_path.suffix.lower().lstrip("."): str(in_path)},
        }

    bin_name = "transd" if diarize else "trans"
    binary = _resolve_bin(bin_name)
    out_dir = Path(output_dir).expanduser() if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    run_name = name or _default_name(input_str, diarize)

    env = _augmented_env()
    env["TRANS_DIR"] = str(out_dir)
    if model:
        env["TRANS_MODEL"] = model
    if on_progress is not None:  # ask transd to emit pyannote's internal progress
        env["TRANS_PROGRESS"] = "1"

    # Stream stdout so we can forward transd's stage/turn progress and honor Cancel.
    try:
        proc = subprocess.Popen(
            [*_arm64_prefix(), binary, input_str, run_name],
            env=env,
            cwd=str(out_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise TransError(f"failed to launch {bin_name}: {exc}") from exc

    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        if stop_event is not None and stop_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise TransError(f"{bin_name} cancelled by user")
        if on_progress:
            try:
                _emit_transd_progress(line, on_progress)
            except Exception:  # noqa: BLE001 — progress must never crash the run
                pass
    proc.wait()

    txt_path = out_dir / f"{run_name}.txt"
    if proc.returncode != 0 or not txt_path.is_file():
        tail = "".join(lines).strip()[-800:]
        raise TransError(
            f"{bin_name} failed (exit {proc.returncode}); no transcript at "
            f"{txt_path}. Output tail:\n{tail}"
        )

    files = {
        ext: str(out_dir / f"{run_name}.{ext}")
        for ext in _FORMATS
        if (out_dir / f"{run_name}.{ext}").is_file()
    }
    return {
        "engine": bin_name,
        "name": run_name,
        "output_dir": str(out_dir),
        "text": txt_path.read_text(encoding="utf-8", errors="replace"),
        "files": files,
    }
