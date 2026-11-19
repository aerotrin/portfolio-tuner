from datetime import datetime
from zoneinfo import ZoneInfo

from frontend.shared.time import format_clock, local_now

TORONTO = ZoneInfo("America/Toronto")


def test_format_clock_strips_hour_leading_zero():
    now = datetime(2026, 11, 19, 14, 5, tzinfo=TORONTO)
    assert format_clock(now) == "Thu, Nov 19 · 2:05 PM EST"


def test_format_clock_morning_and_two_digit_hour():
    now = datetime(2026, 7, 3, 11, 30, tzinfo=TORONTO)
    assert format_clock(now) == "Fri, Jul 3 · 11:30 AM EDT"


def test_local_now_uses_given_zone():
    assert local_now("America/Toronto").tzinfo == TORONTO


def test_local_now_falls_back_without_zone():
    assert local_now(None).tzinfo is not None
    assert local_now("Not/AZone").tzinfo is not None
