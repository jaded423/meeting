"""Claude sign-in helpers — the distribution-critical path.

The app runs on the user's Claude subscription, so the sign-in lapses on a
schedule for the life of every install. On Cody's Mac there is nobody to read a
stderr blob, so these three have to behave: detect it, classify it, and hand
back a double-clickable fix.
"""

from __future__ import annotations

import os
import stat
import subprocess

import pytest

from meeting.assistant import brain


class _FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def auth_path(tmp_path, monkeypatch):
    """Redirect the generated helper into a throwaway dir."""
    path = tmp_path / "cfg" / "auth.command"
    monkeypatch.setattr(brain, "CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(brain, "AUTH_COMMAND", str(path))
    return path


# ── the double-clickable helper ─────────────────────────────────────────────

def test_ensure_auth_command_writes_an_executable_script(auth_path):
    returned = brain.ensure_auth_command()
    assert returned == str(auth_path)
    assert auth_path.is_file()
    assert os.stat(auth_path).st_mode & stat.S_IXUSR, "must be double-clickable"
    body = auth_path.read_text(encoding="utf-8")
    assert body.startswith("#!/bin/sh")
    assert "claude auth login" in body
    # a double-clicked .command may not inherit the shell profile's PATH
    assert "/opt/homebrew/bin" in body
    # never let a stray API key shadow the subscription sign-in
    assert "unset ANTHROPIC_API_KEY" in body


def test_ensure_auth_command_is_idempotent_and_self_healing(auth_path):
    brain.ensure_auth_command()
    auth_path.write_text("clobbered", encoding="utf-8")
    brain.ensure_auth_command()
    assert "claude auth login" in auth_path.read_text(encoding="utf-8")


def test_ensure_auth_command_survives_an_unwritable_config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(brain, "CONFIG_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(brain, "AUTH_COMMAND", str(tmp_path / "nope" / "auth.command"))
    monkeypatch.setattr(brain.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    assert brain.ensure_auth_command()  # returns a path rather than raising


# ── the pre-flight check ────────────────────────────────────────────────────

def test_auth_status_ok_when_logged_in(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _FakeProc('{"loggedIn": true, "authMethod": "claude.ai"}'))
    st = brain.auth_status()
    assert st.ok and st.installed and st.detail == "claude.ai"


def test_auth_status_flags_a_signed_out_cli(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc('{"loggedIn": false}'))
    st = brain.auth_status()
    assert not st.ok and st.installed
    assert "not signed in" in st.detail


def test_auth_status_distinguishes_a_missing_cli(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(subprocess, "run", missing)
    st = brain.auth_status()
    assert not st.ok and not st.installed, "must not tell them to sign in to something absent"


def test_auth_status_does_not_block_on_unparseable_output(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc("not json", returncode=0))
    assert brain.auth_status().ok, "a weird status must not strand a working install"


def test_auth_status_survives_a_timeout(monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=30)
    monkeypatch.setattr(subprocess, "run", slow)
    assert not brain.auth_status().ok


# ── the mid-run backstop ────────────────────────────────────────────────────

@pytest.mark.parametrize("stderr", [
    "Invalid API key · Please run /login",
    "OAuth token expired",
    "Error: not logged in",
    "401 Unauthorized",
])
def test_auth_failures_are_recognised(stderr):
    assert brain.looks_like_auth_failure(brain.BrainResult(False, "", stderr, 0.0))


@pytest.mark.parametrize("stderr", [
    "mlx_whisper failed (exit 1)",
    "ENOENT: no such file or directory",
    "the model returned no parseable array",
])
def test_ordinary_failures_are_not_mistaken_for_auth(stderr):
    assert not brain.looks_like_auth_failure(brain.BrainResult(False, "", stderr, 0.0))
