from datetime import datetime, timezone

import numpy as np
import pandas as pd

from frontend.widgets.treemaps import (
    COLOR_REL_VOLUME,
    REL_VOLUME_COLOR_MAX,
    compact_number,
    render_treemap_intraday,
    render_treemap_positions,
)

GROUPS = ["region", "group_label"]


def _frame(relative_volume: list[float] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "name": ["A", "B", "C"],
            "close": [10.0, 20.0, 30.0],
            "currency": "USD",
            "change": [0.1, -0.2, 0.0],
            "change_percent": [0.01, -0.01, 0.0],
            "volume": [100.0, 200.0, 0.0],
            "timestamp": datetime(2026, 1, 5, tzinfo=timezone.utc),
            "region": "US",
            "group_label": "Core",
        },
        index=pd.Index(["AAA", "BBB", "CCC"], name="symbol"),
    )
    if relative_volume is not None:
        df["relative_volume"] = relative_volume
    return df


def _leaf_colors(fig) -> dict[str, float]:
    trace = fig.data[0]
    return dict(zip(trace.labels, trace.marker.colors))


def test_default_colour_is_change_percent_diverging():
    fig = render_treemap_intraday(_frame([1.0, 2.0, np.nan]), group_cols=GROUPS)

    assert fig.layout.coloraxis.cmid == 0
    assert _leaf_colors(fig)["BBB"] == -0.01


def test_relative_volume_colour_is_sequential_and_clipped():
    fig = render_treemap_intraday(
        _frame([1.5, 7.0, np.nan]), group_cols=GROUPS, color_by=COLOR_REL_VOLUME
    )

    axis = fig.layout.coloraxis
    assert (axis.cmin, axis.cmax) == (0, REL_VOLUME_COLOR_MAX)
    assert axis.cmid is None
    colors = _leaf_colors(fig)
    assert colors["AAA"] == 1.5
    assert colors["BBB"] == REL_VOLUME_COLOR_MAX
    assert colors["CCC"] == 0.0


def test_tile_text_shows_the_multiple_only_when_known():
    fig = render_treemap_intraday(_frame([1.5, 7.0, np.nan]), group_cols=GROUPS)
    text = dict(zip(fig.data[0].labels, (c[0] for c in fig.data[0].customdata)))

    assert "Vol. 100 · 1.5×<br>" in text["AAA"]
    assert "×" not in text["CCC"]


def test_compact_number():
    assert compact_number(950) == "950"
    assert compact_number(1_234) == "1.2K"
    assert compact_number(999_950) == "1.0M"
    assert compact_number(2_627_000) == "2.6M"
    assert compact_number(71_300_000_000) == "71.3B"
    assert compact_number(float("nan")) == "N/A"


def test_frame_without_relative_volume_still_renders():
    fig = render_treemap_intraday(_frame(), group_cols=GROUPS)

    assert "×" not in fig.data[0].customdata[0][0]


def _positions_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "GIC-5.00-20261107", "GIC-4.00-20250101"],
            "name": ["A", "Bank GIC", "Old GIC"],
            "holding_category": ["Equity", "Fixed Income", "Fixed Income"],
            "market_value": [1000.0, 2050.0, 520.0],
            "gain": [100.0, 50.0, 20.0],
            "gain_pct": [0.1, 0.025, 0.04],
            "open_qty": [10, 2000, 500],
            "days_held": [30, 180, 400],
            "weight": [0.3, 0.55, 0.15],
            "option_dte": [np.nan, np.nan, np.nan],
            "fi_rate": [np.nan, 0.05, 0.04],
            "fi_days_to_maturity": [np.nan, 185.0, -35.0],
            "timestamp": datetime(2026, 1, 5, tzinfo=timezone.utc),
        },
        index=pd.Index(["AAA", "GIC-5.00-20261107", "GIC-4.00-20250101"]),
    )


def _leaf_text(fig) -> dict[str, str]:
    trace = fig.data[0]
    return {
        label: data[0]
        for label, data in zip(trace.labels, trace.customdata)
        if label != "Holdings"
    }


def test_positions_treemap_describes_fixed_income_by_rate_and_maturity():
    text = _leaf_text(render_treemap_positions(_positions_frame()))

    assert "10 shares, 30 days" in text["AAA"]
    assert "5.00%, 185 days to maturity" in text["Bank GIC"]
    assert "shares" not in text["Bank GIC"]
    assert "4.00%, matured" in text["Old GIC"]


def test_positions_treemap_hides_fixed_income_amounts_with_balances():
    text = _leaf_text(render_treemap_positions(_positions_frame(), hide_balances=True))

    assert "2,050" not in text["Bank GIC"]
    assert "5.00%, 185 days to maturity" in text["Bank GIC"]


def test_positions_treemap_keeps_keys_for_fixed_income_sharing_a_name():
    df = _positions_frame()
    df["name"] = ["A", "Bank GIC", "Bank GIC"]

    text = _leaf_text(render_treemap_positions(df))

    assert set(text) == {"AAA", "GIC-5.00-20261107", "GIC-4.00-20250101"}
