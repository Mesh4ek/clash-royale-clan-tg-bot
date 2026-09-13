from __future__ import annotations

import json

import pytest

import war_schedule


def test_defaults_come_from_env():
    war_schedule.init_war_schedule()
    assert war_schedule.get_war_day_end() == (9, 30)
    assert war_schedule.get_war_reminder() == (9, 0)
    assert war_schedule.get_notify_hours() == war_schedule.DEFAULT_NOTIFY_HOURS


def test_file_from_older_version_keeps_saved_times():
    old_file = {"war_day_end_utc": 9, "war_day_end_minute": 50, "war_reminder_utc": 9, "war_reminder_minute": 20}
    war_schedule.schedule_path().write_text(json.dumps(old_file))

    war_schedule.init_war_schedule()

    assert war_schedule.get_war_day_end() == (9, 50)
    assert war_schedule.get_war_reminder() == (9, 20)
    assert war_schedule.get_notify_hours() == war_schedule.DEFAULT_NOTIFY_HOURS


def test_unreadable_file_falls_back_to_defaults():
    war_schedule.schedule_path().write_text("{not json")
    war_schedule.init_war_schedule()
    assert war_schedule.get_war_day_end() == (9, 30)


def test_changes_are_saved_and_read_back():
    war_schedule.set_boundary_utc(8, 20)
    war_schedule.set_notify_hours(6)

    saved = json.loads(war_schedule.schedule_path().read_text())
    assert (saved["war_day_end_utc"], saved["war_day_end_minute"], saved["notify_hours"]) == (8, 20, 6)

    war_schedule.init_war_schedule()
    assert war_schedule.get_war_day_end() == (8, 20)
    assert war_schedule.get_notify_hours() == 6


@pytest.mark.parametrize(("end", "reminder"), [((9, 30), (9, 0)), ((0, 10), (23, 40))])
def test_auto_reminder_is_30_minutes_before_end(end, reminder):
    war_schedule.set_boundary_utc(*end)
    war_schedule.set_auto_reminder_30min_before_boundary()
    assert war_schedule.get_war_reminder() == reminder


def test_notify_opening_wraps_past_midnight():
    war_schedule.set_boundary_utc(9, 50)
    war_schedule.set_notify_hours(12)
    assert war_schedule.get_notify_opening() == (21, 50)
