"""The CREATED section of the audit email.

Origin (live run, 2026-07-25): the section was the router's free text pasted
verbatim, so the email Joshua received contained a source path with line numbers,
an explanation of an HTTP 400, "Say the word and I'll patch it", and an offer to
write to a TODO file. Harmless for the developer, fatal for a non-technical
reader — it reads as an internal dev log. `create_items` now returns structured
per-item results and `format_created` renders them; the prose stays in the log.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from meeting.assistant import brain


def _ok(action, type_="event", date="2026-07-28 09:00", guests=(), link="http://x"):
    return {"action": action, "type": type_, "date": date,
            "guests": list(guests), "ok": True, "link": link, "error": None}


# --- rendering ---------------------------------------------------------------

def test_a_created_event_reports_what_landed():
    out = brain.format_created([_ok("Send the deck", guests=["cody@x.com"])])
    assert "✓ Send the deck" in out
    assert "2026-07-28 09:00" in out
    assert "Event" in out
    assert "invited cody@x.com" in out


def test_a_task_without_guests_says_neither():
    out = brain.format_created([_ok("File the receipts", type_="task", date="2026-07-28")])
    assert "Task" in out
    assert "invited" not in out


def test_a_dateless_item_says_no_date_rather_than_none():
    out = brain.format_created([_ok("Follow up", type_="task", date=None)])
    assert "no date" in out
    assert "None" not in out


def test_a_failure_is_reported_not_dropped():
    results = [
        _ok("Send the deck"),
        {"action": "Book the room", "type": "event", "date": "2026-07-29",
         "guests": [], "ok": False, "link": None, "error": "calendar is read-only"},
    ]
    out = brain.format_created(results)
    assert "✗ NOT created — Book the room" in out
    assert "calendar is read-only" in out
    assert "1 of 2 did not get created" in out


def test_no_results_says_so_instead_of_implying_nothing_happened():
    # the items may well have been created — an unparseable reply is "unknown"
    out = brain.format_created([])
    assert "no itemised result" in out
    assert "check Calendar and Tasks" in out


def test_router_prose_can_never_reach_the_rendered_section():
    leak = ("gsuite/tools/calendar_tools.py:133-134 returned a 400. "
            "Say the word and I'll patch it, or write it to ~/projects/gsuite/TODO.md")
    out = brain.format_created([_ok(leak.split(".")[0])])
    # only fields we chose are rendered; nothing echoes the router's offer
    assert "Say the word" not in out
    assert "TODO.md" not in out


# --- the contract with create_items -----------------------------------------

def _fake_run(output):
    return lambda cmd, prompt, timeout: brain.BrainResult(
        ok=True, output=output, error="", seconds=1.0)


def test_create_items_returns_parsed_results_and_the_raw_result():
    payload = json.dumps([_ok("Send the deck")])
    with patch.object(brain, "_run", _fake_run(payload)):
        results, res = brain.create_items([{"action": "Send the deck", "type": "event"}])
    assert res.ok
    assert results[0]["action"] == "Send the deck"
    assert brain.format_created(results).startswith("  ✓")


def test_create_items_survives_an_unparseable_reply():
    with patch.object(brain, "_run", _fake_run("I created everything, boss!")):
        results, res = brain.create_items([{"action": "x", "type": "task"}])
    assert results == []
    assert res.ok           # the run itself succeeded; only the report is missing


def test_guest_emails_and_notes_reach_the_router_payload():
    seen = {}

    def _capture(cmd, prompt, timeout):
        seen["prompt"] = prompt
        return brain.BrainResult(ok=True, output="[]", error="", seconds=1.0)

    with patch.object(brain, "_run", _capture):
        brain.create_items([
            {"action": "Sync", "type": "event", "date": "2026-07-28 09:00",
             "invitees": ["cody@x.com", ""], "notes": ""},
            {"action": "Chase", "type": "task", "date": None,
             "invitees": [], "notes": "With: Cody Sandone"},
        ])
    assert '"guest_emails": [\n      "cody@x.com"\n    ]' in seen["prompt"]  # blanks dropped
    assert '"notes": "With: Cody Sandone"' in seen["prompt"]
    # the router must be told not to reformat the date or invent an end
    assert "UNCHANGED" in seen["prompt"]
    assert "Omit `end`" in seen["prompt"]
