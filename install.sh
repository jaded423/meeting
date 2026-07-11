#!/usr/bin/env sh
# Install meeting on this machine: venv + editable install + register at user
# scope. Idempotent. The server shells out to ~/scripts/bin/{trans,transd}, which
# must be present with their own runtime deps (mlx_whisper; the diarize venv for
# transd). This installs only the MCP wrapper, not the trans stack.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip -q install -e .
BIN="$DIR/.venv/bin/meeting"
# Write a default settings.json (idempotent — never clobbers an existing one) so
# Cody has a file to edit. See `meeting status` for the keys + how to flip them.
./.venv/bin/python -c "from meeting.settings import write_default_settings as w; print('settings:', w())"
claude mcp remove meeting -s user >/dev/null 2>&1 || true
claude mcp add meeting -s user -- "$BIN" serve
echo "meeting: registered (mcp__meeting__* + /meeting prompt). Verify:  claude mcp list"
