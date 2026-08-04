"""Render smoke test for a review row — real Tk widgets, no human.

`_build_row` wires a checkbox, an action entry, a date entry, the time picker and
the type combobox into one `record`, and hangs two traces off it. That wiring is
exactly the kind of thing unit tests miss and a live run finds, so build a real
row on a real (never-shown) root and drive it.
"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
from meeting.assistant.gui.app import ALL_DAY, DEFAULT_TIME, App  # noqa: E402


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no display (headless CI)
        pytest.skip(f"no Tk display: {exc}")
    root.withdraw()
    a = App.__new__(App)          # skip __init__: we want the row machinery only
    a.root = root
    a.rows = []
    a.account = tk.StringVar(value="elevated")
    yield a
    root.destroy()


def _row(app, **item):
    parent = tk.Frame(app.root)
    item.setdefault("action", "Send the deck")
    app._build_row(parent, item, "elevated", "Joshua Brown")
    return app.rows[-1]


def test_a_dated_item_lands_on_the_nine_am_default(app):
    r = _row(app, date="2026-07-28", type="event")
    assert r["date"].get() == "2026-07-28"
    assert r["time"].get() == DEFAULT_TIME
    assert str(r["time_cb"].cget("state")) == "readonly"


def test_a_stated_time_survives_into_the_picker(app):
    r = _row(app, date="2026-07-28 14:30", type="event")
    assert r["time"].get() == "2:30 PM"


def test_items_default_to_event_when_the_model_omits_the_type(app):
    r = _row(app, date="2026-07-28")
    assert r["type"].get() == "event"


def test_switching_to_task_greys_the_time_picker(app):
    r = _row(app, date="2026-07-28", type="event")
    r["type"].set("task")
    app.root.update_idletasks()
    assert str(r["time_cb"].cget("state")) == "disabled"
    r["type"].set("event")
    app.root.update_idletasks()
    assert str(r["time_cb"].cget("state")) == "readonly"


def test_a_task_row_starts_with_its_picker_disabled(app):
    r = _row(app, date="", type="task")
    assert str(r["time_cb"].cget("state")) == "disabled"


def test_gather_joins_the_date_and_the_picked_time(app):
    r = _row(app, date="2026-07-28", type="event")
    r["include"].set(True)
    assert app._gather_items()[0]["date"] == "2026-07-28 09:00"
    r["time"].set(ALL_DAY)
    assert app._gather_items()[0]["date"] == "2026-07-28"


def test_guests_on_a_task_go_to_notes_not_the_title(app):
    r = _row(app, date="2026-07-28", type="task",
             participants=["Cody Sandone"])
    r["include"].set(True)
    r["invitees"] = [{"name": "Cody Sandone", "email": "cody@x.com"}]
    item = app._gather_items()[0]
    assert item["action"] == "Send the deck"          # title stays clean
    assert item["notes"] == "With: Cody Sandone"
    assert item["invitees"] == []                     # Tasks carry no guest list


def test_guests_on_an_event_become_invitees(app):
    r = _row(app, date="2026-07-28", type="event")
    r["include"].set(True)
    r["invitees"] = [{"name": "Cody Sandone", "email": "cody@x.com"}]
    item = app._gather_items()[0]
    assert item["invitees"] == ["cody@x.com"]
    assert item["notes"] == ""
    assert "(w/" not in item["action"]


def test_an_unresolvable_guest_stays_visible_in_the_event_title(app):
    r = _row(app, date="2026-07-28", type="event")
    r["include"].set(True)
    r["invitees"] = [{"name": "Luis", "email": ""}]
    assert app._gather_items()[0]["action"] == "Send the deck (w/ Luis)"


def test_an_unchecked_row_is_not_gathered(app):
    r = _row(app, date="2026-07-28", type="event")
    r["include"].set(False)
    assert app._gather_items() == []
