import numpy as np
import pandas as pd

from frontend.widgets.movers import (
    MOST_ACTIVE,
    UNUSUAL_VOLUME,
    _has_relative_volume,
    _volume_leaders,
)


def _frame(relative_volume: list[float] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(
        {"volume": [9_000_000.0, 50_000.0, 700_000.0, 0.0]},
        index=pd.Index(["BIG", "SMALL", "MID", "INDEX"], name="symbol"),
    )
    if relative_volume is not None:
        df["relative_volume"] = relative_volume
    return df


def test_unusual_volume_ranks_by_relative_volume_not_size():
    out = _volume_leaders(_frame([0.8, 3.5, 1.2, np.nan]), 2, UNUSUAL_VOLUME)

    assert list(out.index) == ["SMALL", "MID"]


def test_unusual_volume_drops_securities_without_the_metric():
    out = _volume_leaders(_frame([0.8, 3.5, 1.2, np.nan]), 10, UNUSUAL_VOLUME)

    assert "INDEX" not in out.index


def test_most_active_ranks_by_raw_volume():
    out = _volume_leaders(_frame([0.8, 3.5, 1.2, np.nan]), 2, MOST_ACTIVE)

    assert list(out.index) == ["BIG", "MID"]


def test_unusual_volume_falls_back_to_raw_volume_without_the_metric():
    assert not _has_relative_volume(_frame())
    assert not _has_relative_volume(_frame([np.nan] * 4))
    assert list(_volume_leaders(_frame(), 2, UNUSUAL_VOLUME).index) == ["BIG", "MID"]
