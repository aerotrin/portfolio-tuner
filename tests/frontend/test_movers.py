import numpy as np
import pandas as pd

from frontend.widgets.movers import _markets_present, _volume_leaders


def _frame(dollar_volume: list[float] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(
        {"volume": [9_000_000.0, 50_000.0, 700_000.0, 0.0]},
        index=pd.Index(["CHEAP", "PRICEY", "MID", "INDEX"], name="symbol"),
    )
    if dollar_volume is not None:
        df["dollar_volume"] = dollar_volume
    return df


def test_ranks_by_dollar_volume_not_share_count():
    out = _volume_leaders(_frame([18e6, 25e6, 21e6, np.nan]), 2)

    assert list(out.index) == ["PRICEY", "MID"]


def test_securities_without_dollar_volume_come_last():
    out = _volume_leaders(_frame([18e6, 25e6, 21e6, np.nan]), 10)

    assert out.index[-1] == "INDEX"


def test_falls_back_to_raw_volume_without_the_metric():
    assert list(_volume_leaders(_frame(), 2).index) == ["CHEAP", "MID"]
    assert list(_volume_leaders(_frame([np.nan] * 4), 2).index) == ["CHEAP", "MID"]


def _currencies(values: list) -> pd.DataFrame:
    return pd.DataFrame({"currency": values})


def test_markets_present_lists_only_markets_with_securities():
    assert _markets_present(_currencies(["CAD", "USD", "USD"])) == ["US", "Canada"]
    assert _markets_present(_currencies(["CAD", "CAD"])) == ["Canada"]


def test_markets_present_ignores_other_and_missing_currencies():
    assert _markets_present(_currencies(["EUR", None])) == []
