from datetime import datetime
from typing import Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import humanize
import pandas as pd
from tzlocal import get_localzone

UTC = ZoneInfo("UTC")
M_TO_SEC = 60
MINS_STALE = 60
COLOR_FRESH: Final = "blue"
COLOR_STALE: Final = "yellow"


def humanize_timestamp(
    time_in: str | datetime | pd.Timestamp | None,
) -> tuple[str, int, Literal["blue", "yellow"]]:
    if time_in is None or time_in is pd.NaT:
        return "N/A", -1, COLOR_STALE

    # Parse / normalize to aware UTC datetime
    if isinstance(time_in, str):
        dt = datetime.fromisoformat(time_in)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)  # assume UTC
        else:
            dt = dt.astimezone(UTC)  # convert to UTC
        time_in_dt = dt

    elif isinstance(time_in, pd.Timestamp):
        dt = time_in.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        time_in_dt = dt

    else:  # datetime
        dt = time_in
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        time_in_dt = dt

    now_utc = datetime.now(UTC)
    stale_mins = int((now_utc - time_in_dt).total_seconds() / M_TO_SEC)
    natural_timestamp = humanize.naturaltime(time_in_dt)

    if stale_mins < MINS_STALE:
        color = COLOR_FRESH
    else:
        color = COLOR_STALE

    return natural_timestamp, stale_mins, color


def local_now(tz_name: str | None) -> datetime:
    """Current time in the given IANA zone (the browser's), else the server's."""
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.now(get_localzone())


def format_last_trade(
    time_in: str | datetime | None, tz_name: str | None = None
) -> str:
    """Last trade time in the given IANA zone (the browser's), else the server's.

    A midnight timestamp is a daily close with no time of day, so only the
    date is shown; naive timestamps are taken as UTC.
    """
    if not time_in:
        return "N/A"
    dt = datetime.fromisoformat(time_in) if isinstance(time_in, str) else time_in
    if (dt.hour, dt.minute, dt.second) == (0, 0, 0):
        return f"{dt:%a, %b} {dt.day}, {dt.year}"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    zone = None
    if tz_name:
        try:
            zone = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return format_clock(dt.astimezone(zone or get_localzone()))


def format_clock(now: datetime) -> str:
    """e.g. 'Thu, Nov 19, 2026 · 2:35 PM EST' (%-I is not portable to Windows)."""
    hour = now.strftime("%I").lstrip("0")
    return f"{now:%a, %b} {now.day}, {now.year} · {hour}:{now:%M %p} {now:%Z}".rstrip()
