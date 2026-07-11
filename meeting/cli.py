"""meeting CLI — `meeting serve` runs the MCP server (what install.sh registers);
`meeting transcribe <input>` is a direct smoke-test path that bypasses MCP."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main() -> None:
    ap = argparse.ArgumentParser(prog="meeting", description="Transcription MCP server.")
    ap.add_argument("--version", action="version", version=f"meeting {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("serve", help="run the stdio MCP server (default)")
    sub.add_parser("status", help="print engine reachability + settings (diagnostic)")

    t = sub.add_parser("transcribe", help="transcribe a URL/file and print the text (smoke test)")
    t.add_argument("input", help="a yt-dlp URL or a local audio/video file")
    t.add_argument("-n", "--name", help="output basename")
    t.add_argument("-d", "--diarize", action="store_true", help="label speakers (transd)")
    t.add_argument("-m", "--model", default="small", help="whisper model (non-diarized)")
    t.add_argument("-o", "--output-dir", help="output directory")

    args = ap.parse_args()

    if args.cmd in (None, "serve"):
        from .server import main as serve_main

        serve_main()
        return

    if args.cmd == "status":
        import json

        from .tools.status_tools import status

        print(json.dumps(status(), indent=2))
        return

    if args.cmd == "transcribe":
        from . import trans_runner

        try:
            res = trans_runner.run(
                args.input,
                name=args.name,
                diarize=args.diarize,
                model=None if args.diarize else args.model,
                output_dir=args.output_dir,
            )
        except trans_runner.TransError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print(res["text"])
        print(f"\n[{res['engine']}] wrote: {', '.join(res['files'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
