"""Every Google-touching call must be pinned to ONE account.

Origin (live run, 2026-07-27): a run with `account="elevated"` emailed the
transcript from joshua@elevatedtrading.com and created the calendar events on
jaded423@gmail.com — a Point4 meeting landed on a personal calendar next to
family birthdays. Cause: `--allowedTools` is a *permission* allowlist, and every
call runs `--dangerously-skip-permissions`, which bypasses permission checks
entirely. Naming `mcp__gsuite-elevated__*` bound nothing; all four `gsuite-*`
servers were loaded and the model picked per tool call.

The binding is now structural — a one-server `--mcp-config` plus
`--strict-mcp-config` — so these tests assert on the *flags*, which is the only
layer that can be checked without a live Google account.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from meeting.assistant import brain

SERVERS = {
    "mcpServers": {
        "gsuite-elevated": {"type": "stdio", "command": "/x/gsuite", "args": ["serve"],
                            "env": {"GSUITE_CONFIG_DIR": "/c/gsuite-elevated"}},
        "gsuite-jaded": {"type": "stdio", "command": "/x/gsuite", "args": ["serve"],
                         "env": {"GSUITE_CONFIG_DIR": "/c/gsuite-jaded"}},
        "other-server": {"type": "stdio", "command": "/x/other"},
    }
}


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """A fake ~/.claude.json + a temp config dir; returns captured argv."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(json.dumps(SERVERS))
    monkeypatch.setattr(brain, "_CLAUDE_CONFIG", str(cfg))
    monkeypatch.setattr(brain, "CONFIG_DIR", str(tmp_path / "cfg"))
    seen = {}

    def _capture(cmd, prompt, timeout):
        seen["cmd"] = cmd
        return brain.BrainResult(ok=True, output="[]", error="", seconds=1.0)

    monkeypatch.setattr(brain, "_run", _capture)
    return seen


def _flag_value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


# --- the config that gets handed to claude ----------------------------------

def test_only_the_selected_account_is_in_the_config(wired):
    path = brain._account_mcp_config("elevated")
    written = json.loads(open(path).read())
    assert list(written["mcpServers"]) == ["gsuite-elevated"]
    # the other account and the unrelated server must both be absent — their
    # presence is what let the model pick wrong
    assert "gsuite-jaded" not in written["mcpServers"]
    assert "other-server" not in written["mcpServers"]


def test_the_server_definition_is_copied_verbatim(wired):
    path = brain._account_mcp_config("jaded")
    entry = json.loads(open(path).read())["mcpServers"]["gsuite-jaded"]
    assert entry["env"]["GSUITE_CONFIG_DIR"] == "/c/gsuite-jaded"


def test_an_unknown_account_refuses_rather_than_guessing(wired):
    with pytest.raises(brain.AccountBindingError) as exc:
        brain._account_mcp_config("nope")
    assert "gsuite-elevated" in str(exc.value)   # names what it did find
    assert "Refusing to run" in str(exc.value)


def test_an_unreadable_config_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(brain, "_CLAUDE_CONFIG", str(tmp_path / "missing.json"))
    with pytest.raises(brain.AccountBindingError):
        brain._account_mcp_config("elevated")


# --- every Google-touching call site ----------------------------------------

def test_create_items_is_bound(wired):
    brain.create_items([{"action": "x", "type": "event"}], account="elevated")
    cmd = wired["cmd"]
    assert "--strict-mcp-config" in cmd
    assert "gsuite-elevated" in _flag_value(cmd, "--mcp-config")


def test_email_transcript_is_bound(wired, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("transcript")
    brain.email_transcript("a@b.com", "s", "b", str(f), account="elevated")
    cmd = wired["cmd"]
    assert "--strict-mcp-config" in cmd
    assert "gsuite-elevated" in _flag_value(cmd, "--mcp-config")


def test_route_is_bound_when_it_writes(wired):
    brain.route("transcript", do_route=True, account="elevated")
    cmd = wired["cmd"]
    assert "--strict-mcp-config" in cmd
    assert "gsuite-elevated" in _flag_value(cmd, "--mcp-config")


def test_propose_only_route_needs_no_binding(wired):
    # it writes nothing, so it gets no Google server at all
    brain.route("transcript", do_route=False)
    assert "--mcp-config" not in wired["cmd"]


# --- the failure must be loud, not silent ------------------------------------

def test_create_items_reports_a_binding_failure_instead_of_running(wired):
    results, res = brain.create_items([{"action": "x"}], account="ghost")
    assert results == []
    assert res.ok is False
    assert "no MCP server named 'gsuite-ghost'" in res.error
    assert "cmd" not in wired          # _run was never reached — nothing was created


def test_email_reports_a_binding_failure_instead_of_sending(wired, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("x")
    res = brain.email_transcript("a@b.com", "s", "b", str(f), account="ghost")
    assert res.ok is False
    assert "cmd" not in wired


def test_the_account_actually_selects_the_server(wired):
    brain.create_items([{"action": "x"}], account="jaded")
    assert "gsuite-jaded" in _flag_value(wired["cmd"], "--mcp-config")
