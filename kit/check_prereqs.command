#!/bin/bash
# check_prereqs.command — read-only. Double-click in Finder. Tells you what the
# install will need to add. Changes nothing.
cd "$(dirname "$0")" || exit 1
echo "════════════  meeting kit — prerequisite check  ════════════"
ok(){  printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad(){ printf "  \033[31m✗\033[0m %s\n" "$1"; }

# Apple Silicon — HARD requirement (mlx-whisper has no Intel build)
if [ "$(uname -m)" = "arm64" ]; then ok "Apple Silicon ($(sysctl -n machdep.cpu.brand_string 2>/dev/null))"
else bad "Intel Mac — the Whisper engine (mlx) will NOT run. An M-series Mac is required."; fi

ok "macOS $(sw_vers -productVersion)"

ram=$(( $(sysctl -n hw.memsize) / 1073741824 ))
if [ "$ram" -ge 16 ]; then ok "${ram} GB RAM"; else bad "${ram} GB RAM (16 GB+ recommended for the default engine)"; fi
ok "$(df -h / | awk 'NR==2{print $4}') free disk on /"

xcode-select -p >/dev/null 2>&1 && ok "Xcode Command Line Tools" || bad "Command Line Tools missing — install.command adds them"
command -v brew    >/dev/null 2>&1 && ok "Homebrew"           || bad "Homebrew missing — install.command adds it"
command -v python3 >/dev/null 2>&1 && ok "python3 $(python3 -V 2>&1 | awk '{print $2}')" || bad "python3 missing"
command -v ffmpeg  >/dev/null 2>&1 && ok "ffmpeg"             || bad "ffmpeg missing — install.command adds it"
command -v yt-dlp  >/dev/null 2>&1 && ok "yt-dlp"             || bad "yt-dlp missing — install.command adds it"
[ -x "$HOME/.venvs/diarize/bin/mlx_whisper" ] && ok "mlx-whisper" || bad "mlx-whisper missing — install.command adds it"
[ -d "/Applications/Claude.app" ] && ok "Claude Desktop app" || echo "  · Claude Desktop not yet installed — install.command adds it"

echo "────────────────────────────────────────────────────────────"
echo "The ONLY hard requirement you can't fix here is an M-series Mac."
echo "Everything else (incl. Claude Desktop) is installed by  install.command"
echo ""
read -n1 -r -p "Press any key to close…" _; echo
