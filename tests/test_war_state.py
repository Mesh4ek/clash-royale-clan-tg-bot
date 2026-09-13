from __future__ import annotations

from datetime import datetime, timezone

import pytest

import war_schedule
import war_state


def at(day, hour, minute=0):
    # September 2026: the 7th is a Monday, so Thursday is the 10th and the next Monday is the 14th.
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def schedule():
    war_schedule.set_boundary_utc(9, 30)
    war_schedule.set_notify_hours(12)


@pytest.mark.parametrize(
    ("moment", "active"),
    [
        (at(8, 12), False),  # Tuesday
        (at(9, 12), False),  # Wednesday
        (at(10, 12), True),  # Thursday
        (at(13, 23), True),  # Sunday
        (at(14, 9, 29), True),  # Monday, before the war ends
        (at(14, 9, 30), False),  # Monday, when the war ends
    ],
)
def test_is_war_active(moment, active):
    assert war_state.is_war_active(moment) is active


@pytest.mark.parametrize(
    ("moment", "expected"),
    [(at(10, 12), False), (at(11, 9), True), (at(14, 9), True), (at(14, 10), False)],
)
def test_auto_reminder_runs_friday_to_monday(moment, expected):
    assert war_state.should_send_auto_reminder(moment) is expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [(at(11, 8), "1 h 30 min"), (at(11, 9), "30 min"), (at(11, 10), "23 h 30 min")],
)
def test_time_left_until_next_day_end(moment, expected):
    assert war_state.time_left_text(moment) == expected


@pytest.mark.parametrize(
    ("moment", "allowed"),
    [
        (at(10, 10), False),  # right after the war day started
        (at(10, 21, 29), False),
        (at(10, 21, 30), True),  # exactly 12 hours before the day ends
        (at(11, 9, 29), True),
        (at(11, 9, 31), False),  # the next war day has started
    ],
)
def test_notify_everyone_window(moment, allowed):
    assert war_state.can_notify_group(moment) is allowed


def test_next_weekly_backup_is_on_thursday_at_day_end():
    assert war_state.next_weekly_backup_run(at(13, 12)) == at(17, 9, 30)
    assert war_state.next_weekly_backup_run(at(10, 9)) == at(10, 9, 30)
    assert war_state.next_weekly_backup_run(at(10, 10)) == at(17, 9, 30)
