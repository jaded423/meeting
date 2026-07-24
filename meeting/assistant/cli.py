"""Meeting Assistant CLI — transcribe (with progress) → route via headless Claude.

    meeting-assistant <input> [options]

    <input>   local audio/video file, a text transcript, or a yt-dlp URL
    --diarize        use transd (speaker labels; slower) instead of fast whisper
    --model NAME     whisper model for the fast path (default: small; try large-v3)
    --account NAME   gsuite account for routing (default: elevated)
    --route          actually create Calendar events / Tasks (default: propose only)
    --name NAME      output basename (default: derived from input)
    --out DIR        transcript output dir (default: ~/projects/trans/transcriptions)
    --skip-brain     transcribe only, don't call Claude

Default is SAFE: it transcribes, then asks Claude to *propose* action items
without creating anything. Add --route to let it write to Calendar/Tasks.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import brain, transcribe
from .transcribe import HOME

_DEFAULT_OUT = HOME / "projects" / "trans" / "transcriptions"


def _fmt(sec: float) -> str:
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _bar(frac: float, width: int = 24) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = int(frac * width)
    return "█" * filled + "░" * (width - filled)


def _make_progress():
    """A live one-line progress renderer. Callback is (phase_label, fraction)."""
    import time
    state = {"phase": None, "t0": time.monotonic()}

    def render(phase: str, frac: float | None) -> None:
        now = time.monotonic()
        if state["phase"] != phase:
            state["phase"], state["t0"] = phase, now
        elapsed = now - state["t0"]
        if frac and frac > 0:
            eta = (elapsed / frac - elapsed) if frac > 0.02 else None
            line = (f"  {phase}: {_bar(frac)} {frac * 100:4.0f}%   "
                    f"elapsed {_fmt(elapsed)}   ETA {_fmt(eta)}   ")
        else:
            line = f"  {phase}…   elapsed {_fmt(elapsed)}   "
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
    return render


def _derive_name(input_str: str) -> str:
    p = Path(input_str)
    if p.exists():
        return p.stem
    tail = input_str.rstrip("/").rsplit("/", 1)[-1]
    slug = "".join(c if c.isalnum() else "-" for c in tail).strip("-")
    return slug[:40] or "meeting"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="meeting-assistant", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="audio/video file, text transcript, or URL")
    ap.add_argument("--diarize", action="store_true", help="speaker labels (transd; slower)")
    ap.add_argument("--model", default="small", help="whisper model (default: small)")
    ap.add_argument("--account", default="elevated", help="gsuite account (default: elevated)")
    ap.add_argument("--route", action="store_true", help="actually create Calendar/Tasks")
    ap.add_argument("--name", default=None, help="output basename")
    ap.add_argument("--out", default=str(_DEFAULT_OUT), help="transcript output dir")
    ap.add_argument("--skip-brain", action="store_true", help="transcribe only")
    args = ap.parse_args(argv)

    name = args.name or _derive_name(args.input)
    out_dir = Path(args.out).expanduser()

    # ── Phase 1: transcription (the heavy local part) ──────────────
    engine = "transd (diarized)" if args.diarize else f"mlx_whisper:{args.model}"
    print(f"▶ Meeting Assistant")
    print(f"  input:  {args.input}")
    print(f"  engine: {engine}")
    print(f"  output: {out_dir}/{name}.txt")
    print()
    print("Transcribing…")
    try:
        result = transcribe.transcribe(
            args.input, name=name, out_dir=out_dir, model=args.model,
            diarize=args.diarize, on_progress=_make_progress(),
        )
    except transcribe.TranscribeError as exc:
        sys.stdout.write("\n")
        print(f"✗ Transcription failed: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write("\n")

    text = result["text"]
    words = len(text.split())
    print(f"✓ Transcript ready — {words:,} words, {result['engine']}, "
          f"{_fmt(result['seconds'])} elapsed")
    print(f"  {result['files'].get('txt', out_dir / (name + '.txt'))}")

    if args.skip_brain:
        return 0
    if not text.strip():
        print("  (empty transcript — nothing to route)", file=sys.stderr)
        return 1

    # ── Phase 2: the brain (headless claude -p, on the subscription) ──
    print()
    mode = "ROUTING → Calendar/Tasks" if args.route else "PROPOSING (no writes)"
    print(f"Brain [{mode}] — running claude -p …")
    r = brain.route(text, account=args.account, diarized=args.diarize,
                    do_route=args.route)
    if not r.ok:
        print(f"✗ Brain failed ({_fmt(r.seconds)}): {r.error or 'see above'}",
              file=sys.stderr)
        return 1

    print(f"✓ Brain done ({_fmt(r.seconds)}):\n")
    print(r.output)
    if not args.route:
        print("\n(Nothing was created. Re-run with --route to write these to "
              "Calendar/Tasks.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
