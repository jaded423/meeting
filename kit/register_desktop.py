#!/usr/bin/env python3
"""Merge the meeting + gsuite MCP servers into Claude Desktop's config.

Claude Desktop reads ~/Library/Application Support/Claude/claude_desktop_config.json
(NOT `claude mcp add`, which is the Claude Code CLI). We merge — never clobber —
so any MCP servers the user already has are preserved.
"""
import argparse, json, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--config", required=True)
ap.add_argument("--meeting-bin", required=True)
ap.add_argument("--gsuite-bin", required=True)
ap.add_argument("--gsuite-config", required=True)
a = ap.parse_args()

cfg_path = Path(a.config)
cfg_path.parent.mkdir(parents=True, exist_ok=True)

cfg = {}
if cfg_path.exists() and cfg_path.stat().st_size:
    try:
        cfg = json.loads(cfg_path.read_text())
    except json.JSONDecodeError:
        backup = cfg_path.with_suffix(".json.bak")
        cfg_path.replace(backup)
        print(f"! existing config was invalid JSON — backed up to {backup}, starting fresh")
        cfg = {}

servers = cfg.setdefault("mcpServers", {})
servers["meeting"] = {"command": a.meeting_bin, "args": ["serve"]}
servers["gsuite"] = {
    "command": a.gsuite_bin,
    "args": ["serve"],
    "env": {"GSUITE_CONFIG_DIR": a.gsuite_config},
}

cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"registered meeting + gsuite in {cfg_path}")
