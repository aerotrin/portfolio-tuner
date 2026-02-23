from datetime import datetime
from zoneinfo import ZoneInfo

import humanize
import pandas as pd

UTC = ZoneInfo("UTC")
M_TO_SEC = 60
MINS_STALE = 60
COLOR_FRESH = "blue"
COLOR_STALE = "yellow"


def humanize_timestamp(time_in: str | datetime | pd.Timestamp) -> tuple[str, int, str]:
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
