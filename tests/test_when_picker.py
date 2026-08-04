"""The date + time-of-day picker on a review row.

`_split_when` / `_join_when` are the whole contract between what the model
proposes, what the human sees in the dropdown, and what `calendar_create_event`
receives as `start`. They are pure functions, so no display is needed.

The shapes that matter downstream (verified live against Google on 2026-07-25):
`YYYY-MM-DD` is an all-day event, `YYYY-MM-DD HH:MM` is a timed one, and neither
carries a timezone — gsuite stamps the calendar's own.
"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
from meeting.assistant.gui.app import (  # noqa: E402
    ALL_DAY, DEFAULT_TIME, TIMES, _join_when, _split_when,
)


# --- the picker itself -------------------------------------------------------

def test_all_day_is_the_first_choice_not_the_default():
    assert TIMES[0] == ALL_DAY
    assert DEFAULT_TIME == "9:00 AM"
    assert DEFAULT_TIME in TIMES


def test_slots_are_half_hourly_across_the_working_day():
    assert "7:00 AM" in TIMES and "6:30 PM" in TIMES
    assert "12:00 PM" in TIMES and "12:30 PM" in TIMES   # noon, not 0:00
    assert "6:45 PM" not in TIMES
    assert len(TIMES) == 25                              # All day + 24 half-hours


# --- splitting what the model proposed --------------------------------------

def test_a_bare_date_defaults_to_nine_am():
    # no time in the string means the model heard no time — that is the 9:00
    # default, NOT an all-day event
    assert _split_when("2026-07-28") == ("2026-07-28", "9:00 AM")


def test_a_stated_time_is_preserved():
    assert _split_when("2026-07-28 14:30") == ("2026-07-28", "2:30 PM")


def test_iso_t_separator_is_understood():
    assert _split_when("2026-07-28T09:00") == ("2026-07-28", "9:00 AM")


def test_seconds_are_tolerated():
    assert _split_when("2026-07-28 14:30:00") == ("2026-07-28", "2:30 PM")


def test_an_off_grid_time_falls_back_to_the_default():
    # 14:37 has no dropdown slot; the date is still kept
    assert _split_when("2026-07-28 14:37") == ("2026-07-28", DEFAULT_TIME)


def test_garbage_time_keeps_the_date():
    assert _split_when("2026-07-28 lunchtime") == ("2026-07-28", DEFAULT_TIME)


def test_no_date_at_all():
    assert _split_when("") == ("", DEFAULT_TIME)
    assert _split_when(None) == ("", DEFAULT_TIME)


# --- joining it back for the API --------------------------------------------

def test_a_time_pick_becomes_a_timed_start():
    assert _join_when("2026-07-28", "9:00 AM") == "2026-07-28 09:00"


def test_afternoon_picks_convert_to_24_hour():
    assert _join_when("2026-07-28", "2:30 PM") == "2026-07-28 14:30"
    assert _join_when("2026-07-28", "12:00 PM") == "2026-07-28 12:00"


def test_all_day_emits_a_date_only_start():
    # date-only is exactly what gsuite turns into a real all-day event
    assert _join_when("2026-07-28", ALL_DAY) == "2026-07-28"


def test_no_date_means_no_start():
    assert _join_when("", "9:00 AM") is None
    assert _join_when("   ", ALL_DAY) is None


def test_round_trip_is_stable():
    for label in TIMES:
        day, back = _split_when(_join_when("2026-07-28", label) or "")
        assert day == "2026-07-28"
        # All day round-trips to the 9:00 default (a date-only value carries no
        # time), every real slot round-trips to itself
        assert back == (DEFAULT_TIME if label == ALL_DAY else label)
