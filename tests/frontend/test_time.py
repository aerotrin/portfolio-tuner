from datetime import datetime
from zoneinfo import ZoneInfo

from frontend.shared.time import format_clock, format_last_trade, local_now

TORONTO = ZoneInfo("America/Toronto")


def test_format_clock_strips_hour_leading_zero():
    now = datetime(2026, 11, 19, 14, 5, tzinfo=TORONTO)
    assert format_clock(now) == "Thu, Nov 19, 2026 · 2:05 PM EST"


def test_format_clock_morning_and_two_digit_hour():
    now = datetime(2026, 7, 3, 11, 30, tzinfo=TORONTO)
    assert format_clock(now) == "Fri, Jul 3, 2026 · 11:30 AM EDT"


def test_local_now_uses_given_zone():
    assert local_now("America/Toronto").tzinfo == TORONTO


def test_local_now_falls_back_without_zone():
    assert local_now(None).tzinfo is not None
    assert local_now("Not/AZone").tzinfo is not None


def test_format_last_trade_converts_to_the_given_zone() -> None:
    text = format_last_trade("2026-11-19T19:35:00+00:00", "America/Toronto")

    assert text == "Thu, Nov 19, 2026 · 2:35 PM EST"


def test_format_last_trade_treats_naive_timestamps_as_utc() -> None:
    text = format_last_trade("2026-11-19T19:35:00", "America/Toronto")

    assert text == "Thu, Nov 19, 2026 · 2:35 PM EST"


def test_format_last_trade_shows_only_the_date_for_a_daily_close() -> None:
    assert format_last_trade("2026-11-19T00:00:00", "America/Toronto") == (
        "Thu, Nov 19, 2026"
    )


def test_format_last_trade_handles_missing_values() -> None:
    assert format_last_trade(None) == "N/A"
