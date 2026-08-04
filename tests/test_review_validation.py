"""Review-panel validation — the dateless-event guard.

`App._row_problem` is a pure staticmethod over Tk variables, so it can be tested
with plain stubs (no display, no widgets). The rule it encodes cost a real live
run: `calendar_create_event` needs a `start`, so an item that is `type: event`
with `date: null` is impossible to create — the router either invents a date (and
mails the invite to a real person) or stops and asks. Neither is acceptable, so
Create must be unclickable until the row is fixed.

`end` stopped being required on 2026-07-25 (gsuite now defaults it), and events
are the default type as of 2026-07-27 — but a date is still mandatory for one, so
this guard survives both changes. It now reads as "supply the date that lets this
item invite someone" rather than "the API will reject this".
"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
from meeting.assistant.gui.app import App  # noqa: E402


class _Var:
    """Stand-in for a tk.StringVar / BooleanVar."""

    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


def _row(type_="task", date=""):
    return {"type": _Var(type_), "date": _Var(date)}


def test_event_without_a_date_is_a_problem():
    assert App._row_problem(_row("event", "")) == "an event with no date"


def test_event_with_only_whitespace_for_a_date_is_a_problem():
    assert App._row_problem(_row("event", "   ")) == "an event with no date"


@pytest.mark.parametrize("row", [
    _row("event", "2026-07-28"),          # dated event — fine
    _row("event", "2026-07-28 14:30"),    # dated + timed event — fine
    _row("task", ""),                     # a dateless task is the normal case
    _row("task", "2026-07-28"),           # a task with a due date — fine
])
def test_creatable_rows_have_no_problem(row):
    assert App._row_problem(row) == ""
