#!/bin/bash
# build_kit.sh — assemble a SELF-CONTAINED meeting install kit on Joshua's Mac.
#
# Vendors meeting + gsuite source + the trans/transd scripts into kit/vendor/ so
# the target Mac needs NO git and NO access to the private repos — it installs
# entirely from the bundled copies. Run this whenever meeting/gsuite/trans change,
# then zip the kit dir (or push it to a repo Cody can reach) for distribution.
#
# Usage:  bash ~/projects/meeting/kit/build_kit.sh
set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
VENDOR="$KIT/vendor"
SRC="$HOME/projects"

echo "▶ Building self-contained kit in $KIT"
mkdir -p "$VENDOR"

# rsync excludes: throwaway/build/secret dirs we never want in the kit.
EXCLUDES=(--exclude '.git' --exclude '.venv' --exclude '__pycache__'
          --exclude '*.egg-info' --exclude '.pytest_cache' --exclude '.DS_Store'
          --exclude 'tokens.json' --exclude 'transcriptions' --exclude 'test-fathom'
          --exclude 'kit')   # meeting/kit is THIS kit — never vendor it into itself

for repo in meeting gsuite; do
  echo "  • vendoring $repo/"
  rm -rf "$VENDOR/$repo"
  rsync -a "${EXCLUDES[@]}" "$SRC/$repo/" "$VENDOR/$repo/"
done

# trans/transd scripts + vocab (already copied once; refresh them here so build is idempotent)
echo "  • vendoring trans-bin/ (trans, transd, vocab.txt)"
mkdir -p "$VENDOR/trans-bin"
cp "$HOME/scripts/bin/trans" "$HOME/scripts/bin/transd" "$VENDOR/trans-bin/"
cp "$SRC/trans/vocab.txt" "$VENDOR/trans-bin/vocab.txt"

# gsuite OAuth client (installed-app, non-rotating, Google-"not confidential") + a clean
# default settings.json. This is the ONLY credential-ish file in the kit; NO user tokens.
echo "  • vendoring gsuite-config/ (installed-app OAuth client + default settings)"
mkdir -p "$VENDOR/gsuite-config"
cp "$HOME/.config/gsuite-elevated/oauth-client.json" "$VENDOR/gsuite-config/oauth-client.json"
# ship a clean settings.json (features on; no account-specific data)
cp "$HOME/.config/gsuite-elevated/settings.json" "$VENDOR/gsuite-config/settings.json"

echo "✓ Kit built. Contents:"
du -sh "$VENDOR"/* 2>/dev/null || true
echo ""
echo "Distribute:  zip -r meeting-kit.zip '$KIT' -x '*/.git/*'   → share the zip"
echo "Target Mac:  unzip → double-click check_prereqs.command → install.command"
