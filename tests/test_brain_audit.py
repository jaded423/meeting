"""Completeness-safety-net tests — patch subprocess so no real `claude -p` runs.

These cover the contract the GUI leans on: the audit never raises, never blocks the
items the first pass found, and the transcript email passes the file by PATH (never
through the model's context, which would be both expensive and lossy).
"""

from __future__ import annotations

import subprocess

import pytest

from meeting.assistant import brain


class _FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _capture(monkeypatch, stdout="", returncode=0):
    """Patch subprocess.run; return a dict that records the cmd + stdin prompt."""
    seen: dict = {}

    def fake_run(cmd, input=None, env=None, **kw):
        seen["cmd"] = cmd
        seen["prompt"] = input
        seen["env"] = env
        return _FakeProc(stdout=stdout, returncode=returncode)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


# ── JSON extraction ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    '{"topics": [], "missed": []}',
    'Here you go:\n```json\n{"topics": [], "missed": []}\n```\nHope that helps!',
    'prose before {"topics": [], "missed": []} prose after',
])
def test_extract_json_object_tolerates_wrapping(raw):
    assert brain._extract_json_object(raw) == {"topics": [], "missed": []}


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2]", "{not json}"])
def test_extract_json_object_returns_none_on_junk(raw):
    assert brain._extract_json_object(raw) is None


# ── normalisation ───────────────────────────────────────────────────────────

def test_normalize_coerces_and_drops_malformed():
    cov = brain._normalize_coverage({
        "topics": [
            {"topic": "Pillars", "status": "MISSED", "note": "Luis to draft"},
            {"topic": "Chit-chat", "status": "no-action"},
            {"topic": "Odd", "status": "not-a-status"},   # unknown → missed
            {"topic": "   ", "status": "covered"},        # blank → dropped
            "garbage",                                    # wrong type → dropped
        ],
        "missed": [
            {"owner": "Luis", "action": "Draft the four-pillars design"},
            {"owner": "Nobody", "action": "   "},          # no action → dropped
            "garbage",
        ],
    })
    assert [t["status"] for t in cov["topics"]] == ["missed", "no-action", "missed"]
    assert cov["topics"][0]["note"] == "Luis to draft"
    assert len(cov["missed"]) == 1


def test_normalize_survives_none_and_empty():
    assert brain._normalize_coverage(None) == {"topics": [], "missed": []}
    assert brain._normalize_coverage({}) == {"topics": [], "missed": []}


# ── the audit pass ──────────────────────────────────────────────────────────

def test_audit_prompt_carries_first_pass_and_transcript(monkeypatch):
    seen = _capture(monkeypatch, stdout='{"topics": [], "missed": []}')
    brain.audit_coverage(
        "SPEAKER_00: we agreed Luis writes the design",
        [{"owner": "Joshua Brown", "action": "Send the deck", "date": "2026-07-25",
          "type": "event"}],
        diarized=True, me_name="Joshua Brown", anchor_date="2026-07-24",
        roster_names=["Luis Rivera"],
    )
    prompt = seen["prompt"]
    assert "1. [Joshua Brown] Send the deck — 2026-07-25 (event)" in prompt
    assert "we agreed Luis writes the design" in prompt
    assert "2026-07-24" in prompt              # anchors relative dates
    assert "Luis Rivera" in prompt             # roster for name resolution
    assert "UNDER-include" in prompt           # the adversarial framing
    # read-only: the audit must not be able to write anything
    assert "--disallowedTools" in seen["cmd"]
    assert not any("calendar_create" in c or "tasks_create" in c for c in seen["cmd"])
    assert seen["env"]["ANTHROPIC_API_KEY"] == ""   # subscription auth, unmetered


def test_audit_tells_the_critic_when_the_first_pass_was_empty(monkeypatch):
    seen = _capture(monkeypatch, stdout="{}")
    brain.audit_coverage("some talk", [])
    assert "treat every commitment as missed" in seen["prompt"]


def test_audit_returns_empty_ledger_on_unparseable_output(monkeypatch):
    _capture(monkeypatch, stdout="I could not do that, sorry.")
    cov, res = brain.audit_coverage("transcript", [{"action": "x"}])
    assert cov == {"topics": [], "missed": []}
    assert res.ok is True          # the call itself succeeded; the JSON just wasn't there


def test_audit_returns_empty_ledger_when_claude_fails(monkeypatch):
    _capture(monkeypatch, stdout="", returncode=1)
    cov, res = brain.audit_coverage("transcript", [{"action": "x"}])
    assert cov == {"topics": [], "missed": []}
    assert res.ok is False


def test_audit_survives_a_launch_failure(monkeypatch):
    def boom(*a, **kw):
        raise OSError("claude: not found")
    monkeypatch.setattr(subprocess, "run", boom)
    cov, res = brain.audit_coverage("transcript", [])
    assert cov == {"topics": [], "missed": []}
    assert res.ok is False and "not found" in res.error


def test_audit_timeout_is_reported_not_raised(monkeypatch):
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=900)
    monkeypatch.setattr(subprocess, "run", timeout)
    cov, res = brain.audit_coverage("transcript", [], timeout=900)
    assert cov == {"topics": [], "missed": []}
    assert "timed out" in res.error


# ── the transcript email ────────────────────────────────────────────────────

def test_email_passes_the_path_not_the_transcript(monkeypatch, tmp_path):
    f = tmp_path / "meeting.txt"
    f.write_text("SPEAKER_00: a very long transcript " * 500, encoding="utf-8")
    seen = _capture(monkeypatch, stdout="msg-123")

    res = brain.email_transcript(
        "joshua@elevatedtrading.com", "Meeting transcript — demo (2026-07-24)",
        "COVERAGE — 3 topics", str(f), account="elevated",
    )
    assert res.ok
    prompt = seen["prompt"]
    assert str(f) in prompt
    # the whole point: the transcript body never enters the model's context
    assert "a very long transcript" not in prompt
    assert "COVERAGE — 3 topics" in prompt
    assert "mcp__gsuite-elevated__gmail_send_message" in seen["cmd"]
    # it has no reason to open the file it is attaching
    assert "Read" in seen["cmd"]


def test_email_refuses_a_missing_attachment(monkeypatch, tmp_path):
    called = _capture(monkeypatch, stdout="should not happen")
    res = brain.email_transcript("a@b.com", "s", "b", str(tmp_path / "nope.txt"))
    assert res.ok is False
    assert "no transcript file" in res.error
    assert "cmd" not in called          # never spawned claude at all


def test_email_refuses_an_empty_path(monkeypatch):
    called = _capture(monkeypatch)
    res = brain.email_transcript("a@b.com", "s", "b", "")
    assert res.ok is False
    assert "cmd" not in called


# ── the report ──────────────────────────────────────────────────────────────

def test_format_coverage_reports_topics_items_and_created():
    cov = {"topics": [{"topic": "Pillars", "status": "missed", "note": "Luis to draft"},
                      {"topic": "Pricing", "status": "covered", "note": ""}],
           "missed": []}
    out = brain.format_coverage(
        cov,
        [{"owner": "Luis", "action": "Draft the design", "date": None, "type": "task"}],
        created="1. Draft the design · no date · Task",
    )
    assert "2 topics discussed, 1 flagged as missed" in out
    assert "⚠ Pillars — Luis to draft" in out
    assert "✓ Pricing" in out
    assert "[Luis] Draft the design" in out
    assert "CREATED IN CALENDAR / TASKS" in out


def test_format_coverage_says_so_when_the_audit_returned_nothing():
    out = brain.format_coverage({"topics": [], "missed": []}, [])
    assert "no topic ledger" in out
