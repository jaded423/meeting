#!/bin/bash
# install.command — the install wizard.  Nothing → running, on a fresh
# Apple-Silicon Mac.  Double-click in Finder.  Idempotent: every step checks
# before it installs, so re-running never duplicates.  Ends with a self-test
# that proves the pipeline actually works.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
STEP=0; TOTAL=10
step(){ STEP=$((STEP+1)); printf "\n\033[1m━━━ %s/%s  %s ━━━\033[0m\n" "$STEP" "$TOTAL" "$1"; }
ok(){   printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m!\033[0m %s\n" "$1"; }
die(){  printf "\n\033[31m✗ %s\033[0m\n" "$1"; read -n1 -r -p "Press any key to close…" _; echo; exit 1; }

# ── 0. Preflight ────────────────────────────────────────────────
step "Preflight"
[ "$(uname)" = "Darwin" ] || die "macOS only."
[ "$(uname -m)" = "arm64" ] || die "Intel Mac detected. The Whisper engine (mlx-whisper) is Apple-Silicon only — an M-series Mac is required."
ok "Apple Silicon, macOS $(sw_vers -productVersion)"

# ── 1. Xcode Command Line Tools (git + compilers; Homebrew needs them) ──
step "Command Line Tools"
if xcode-select -p >/dev/null 2>&1; then ok "already present"; else
  warn "A macOS dialog will open — click \"Install\" and wait for it to finish."
  xcode-select --install || true
  echo ""; echo "→ When Command Line Tools finish, double-click install.command AGAIN to continue."
  read -n1 -r -p "Press any key to close…" _; echo; exit 0
fi

# ── 2. Homebrew ─────────────────────────────────────────────────
step "Homebrew"
if command -v brew >/dev/null 2>&1; then ok "already installed"; else
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || die "Homebrew install failed."
fi
eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
command -v brew >/dev/null 2>&1 || die "brew not on PATH after install."
ok "$(brew --version | head -1)"

# ── 3. Claude Desktop + media tools (idempotent — skip if present) ──
step "Claude Desktop + ffmpeg + yt-dlp"
if [ -d "/Applications/Claude.app" ]; then ok "Claude Desktop already installed"; else
  warn "Installing Claude Desktop (may ask for your Mac password to move it to /Applications)…"
  brew install --cask claude || die "Claude Desktop (brew --cask claude) install failed."
  ok "Claude Desktop installed"
fi
for f in ffmpeg yt-dlp; do
  command -v "$f" >/dev/null 2>&1 && ok "$f present" || { brew install "$f" || die "brew install $f failed."; ok "$f installed"; }
done

# ── 4. Whisper engine (mlx-whisper) → ~/.venvs/diarize ──────────
step "Whisper engine (mlx-whisper)"
[ -d "$HOME/.venvs/diarize" ] || python3 -m venv "$HOME/.venvs/diarize"
"$HOME/.venvs/diarize/bin/pip" install --quiet --upgrade pip
if [ -x "$HOME/.venvs/diarize/bin/mlx_whisper" ]; then ok "mlx-whisper present"; else
  "$HOME/.venvs/diarize/bin/pip" install --quiet -r "$HERE/requirements.txt" || die "mlx-whisper install failed."
  ok "mlx-whisper installed"
fi

# ── 5. trans scripts → ~/scripts/bin ────────────────────────────
step "trans / transd scripts"
mkdir -p "$HOME/scripts/bin" "$HOME/projects/trans"
install -m 0755 "$HERE/vendor/trans-bin/trans"  "$HOME/scripts/bin/trans"
install -m 0755 "$HERE/vendor/trans-bin/transd" "$HOME/scripts/bin/transd"
cp "$HERE/vendor/trans-bin/vocab.txt" "$HOME/projects/trans/vocab.txt"
ok "trans + transd installed"

# ── 6. MCP servers (gsuite + meeting) ───────────────────────────
step "MCP servers (gsuite + meeting)"
mkdir -p "$HOME/projects"
for repo in gsuite meeting; do
  # refresh source (managed dir), keep the venv across re-runs for speed
  rsync -a --delete --exclude '.venv' "$HERE/vendor/$repo/" "$HOME/projects/$repo/"
  [ -d "$HOME/projects/$repo/.venv" ] || python3 -m venv "$HOME/projects/$repo/.venv"
  "$HOME/projects/$repo/.venv/bin/pip" install --quiet --upgrade pip
  "$HOME/projects/$repo/.venv/bin/pip" install --quiet -e "$HOME/projects/$repo" || die "$repo pip install failed."
  ok "$repo installed"
done
"$HOME/projects/meeting/.venv/bin/python" -c "from meeting.settings import write_default_settings as w; w()" 2>/dev/null || true

# ── 7. gsuite OAuth client → ~/.config/gsuite ───────────────────
step "gsuite config"
mkdir -p "$HOME/.config/gsuite"
if [ -f "$HERE/vendor/gsuite-config/oauth-client.json" ]; then
  cp "$HERE/vendor/gsuite-config/oauth-client.json" "$HOME/.config/gsuite/oauth-client.json"
  [ -f "$HOME/.config/gsuite/settings.json" ] || cp "$HERE/vendor/gsuite-config/settings.json" "$HOME/.config/gsuite/settings.json"
  ok "OAuth client in place"
else
  warn "No OAuth client bundled — drop yours at ~/.config/gsuite/oauth-client.json and re-run."
fi

# ── 8. Register both servers in Claude Desktop ──────────────────
step "Register in Claude Desktop"
DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
python3 "$HERE/register_desktop.py" --config "$DESKTOP_CFG" \
  --meeting-bin "$HOME/projects/meeting/.venv/bin/meeting" \
  --gsuite-bin  "$HOME/projects/gsuite/.venv/bin/gsuite" \
  --gsuite-config "$HOME/.config/gsuite" || die "Claude Desktop registration failed."
ok "meeting + gsuite registered"

# ── 9. Google sign-in (skip if a valid token already exists) ────
step "Google sign-in"
if GSUITE_CONFIG_DIR="$HOME/.config/gsuite" "$HOME/projects/gsuite/.venv/bin/python" \
     -c "from gsuite.auth import get_credentials; get_credentials()" >/dev/null 2>&1; then
  ok "already signed in (valid token) — skipping"
elif [ -f "$HOME/.config/gsuite/oauth-client.json" ]; then
  warn "A browser will open — sign into the Google account for THIS Mac and grant access."
  GSUITE_CONFIG_DIR="$HOME/.config/gsuite" "$HOME/projects/gsuite/.venv/bin/gsuite" auth \
    || warn "OAuth didn't finish. Re-run this installer, or: GSUITE_CONFIG_DIR=~/.config/gsuite ~/projects/gsuite/.venv/bin/gsuite auth"
else
  warn "Skipped — no OAuth client (see step 7)."
fi

# ── 10. Self-test — prove the app actually works ────────────────
step "Self-test"
FAIL=0
# a) Whisper engine transcribes a real (spoken) clip
say -o /tmp/meeting-selftest.aiff "Testing the meeting transcription engine for Elevated Trading." 2>/dev/null
if PATH="$HOME/.venvs/diarize/bin:/opt/homebrew/bin:$PATH" TRANS_DIR=/tmp \
     "$HOME/scripts/bin/trans" /tmp/meeting-selftest.aiff meeting-selftest >/dev/null 2>&1 \
     && [ -s /tmp/meeting-selftest.txt ]; then ok "transcription engine works"; else warn "transcription self-test FAILED"; FAIL=1; fi
rm -f /tmp/meeting-selftest.aiff /tmp/meeting-selftest.*
# b) gsuite token is live
if GSUITE_CONFIG_DIR="$HOME/.config/gsuite" "$HOME/projects/gsuite/.venv/bin/python" \
     -c "from gsuite.auth import get_credentials; get_credentials()" >/dev/null 2>&1; then
  ok "gsuite Google connection works"; else warn "gsuite not authorized (finish sign-in above)"; FAIL=1; fi
# c) Claude Desktop has both servers registered
if python3 -c "import json,sys; d=json.load(open('$DESKTOP_CFG')); sys.exit(0 if {'meeting','gsuite'} <= set(d.get('mcpServers',{})) else 1)" 2>/dev/null; then
  ok "Claude Desktop knows about meeting + gsuite"; else warn "Claude Desktop registration missing"; FAIL=1; fi

echo ""
if [ "$FAIL" = 0 ]; then
  printf "\033[1;32m✓ All checks passed — the app is ready.\033[0m\n"
else
  printf "\033[1;33m! Some checks didn't pass (see ! lines above). Re-run install.command after fixing.\033[0m\n"
fi
echo ""
echo "Last step (only a human can do it): QUIT and REOPEN Claude Desktop so it loads the servers."
echo "Then in a chat:   /meeting $HERE/sample-meeting.txt"
echo ""
read -n1 -r -p "Press any key to close…" _; echo
