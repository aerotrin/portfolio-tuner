from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

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
            "fi_maturity_date": [None, "2026-11-07", "2025-01-01"],
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


def _rows(text: str) -> list[str]:
    return text.split("<br>")


def test_positions_treemap_tile_rows():
    text = _leaf_text(render_treemap_positions(_positions_frame()))

    assert _rows(text["AAA"])[:4] == [
        "1,000.00 CAD",
        "+100.00 +10.00%",
        "10 sh · 30 d",
        "Wt. 30.00%",
    ]
    assert len(_rows(text["AAA"])) == 5
    assert _rows(text["Bank GIC"]) == [
        "2,050.00 CAD",
        "+50.00 +2.50%",
        "5.00% · 185 d left",
        "Wt. 55.00%",
        "Mat. 2026-11-07",
    ]
    assert _rows(text["Old GIC"])[2] == "4.00% · matured"


def test_positions_treemap_with_balances_hidden_keeps_the_same_rows():
    text = _leaf_text(render_treemap_positions(_positions_frame(), hide_balances=True))

    stock, gic = _rows(text["AAA"]), _rows(text["Bank GIC"])
    assert stock[1:4] == ["+10.00%", "30 d", "Wt. 30.00%"]
    assert len(stock) == 5
    assert "2,050" not in text["Bank GIC"] and "+50.00" not in text["Bank GIC"]
    assert gic[1:] == [
        "+2.50%",
        "5.00% · 185 d left",
        "Wt. 55.00%",
        "Mat. 2026-11-07",
    ]


def test_positions_treemap_keeps_keys_for_fixed_income_sharing_a_name():
    df = _positions_frame()
    df["name"] = ["A", "Bank GIC", "Bank GIC"]

    text = _leaf_text(render_treemap_positions(df))

    assert set(text) == {"AAA", "GIC-5.00-20261107", "GIC-4.00-20250101"}


def _holdings_frame() -> pd.DataFrame:
    """A stock and two GICs as the Positions tab passes them: the GIC rows
    have no quote, so their quote columns are missing."""
    return pd.DataFrame(
        {
            "symbol": ["AAA", "GIC-5.00-20261107", "GIC-4.00-20250101"],
            "name": ["A", "Bank GIC", "Old GIC"],
            "account": ["TFSA #1", "TFSA #1", "LIRA #2"],
            "holding_category": ["Equity", "Fixed Income", "Fixed Income"],
            "close": [10.0, np.nan, np.nan],
            "currency": ["USD", "CAD", "CAD"],
            "change": [0.1, np.nan, np.nan],
            "change_percent": [0.01, np.nan, np.nan],
            "volume": [100.0, np.nan, np.nan],
            "timestamp": [datetime(2026, 1, 5, tzinfo=timezone.utc), pd.NaT, pd.NaT],
            "market_value": [1000.0, 2050.0, 520.0],
            "gain": [100.0, 50.0, 20.0],
            "gain_pct": [0.1, 0.025, 0.04],
            "open_qty": [10, 2000, 500],
            "days_held": [30, 180, 400],
            "weight": [0.3, 0.55, 0.15],
            "option_dte": [np.nan, np.nan, np.nan],
            "fi_rate": [np.nan, 0.05, 0.04],
            "fi_days_to_maturity": [np.nan, 185.0, -35.0],
            "fi_maturity_date": [None, "2026-11-07", "2025-01-01"],
        },
        index=pd.Index(["AAA", "GIC-5.00-20261107", "GIC-4.00-20250101"]),
    )


def _tile_text(fig) -> dict[str, str]:
    trace = fig.data[0]
    return {label: data[0] for label, data in zip(trace.labels, trace.customdata)}


def test_intraday_treemap_shows_fixed_income_as_a_neutral_tile():
    fig = render_treemap_intraday(_holdings_frame(), has_weight=True)

    text = _tile_text(fig)
    assert _rows(text["AAA"])[:4] == [
        "10.00 USD",
        "+0.10 +1.00%",
        "Vol. 100",
        "Wt. 30.00%",
    ]
    assert len(_rows(text["AAA"])) == 5
    assert _rows(text["Bank GIC"]) == [
        "2,050.00 CAD",
        "No intraday chg",
        "5.00% · 185 d left",
        "Wt. 55.00%",
        "Mat. 2026-11-07",
    ]
    assert _rows(text["Old GIC"])[2] == "4.00% · matured"
    assert "nan" not in "".join(text[k] for k in ("AAA", "Bank GIC", "Old GIC"))
    colors = _leaf_colors(fig)
    assert colors["Bank GIC"] == 0.0
    assert colors["AAA"] == 0.01


def test_intraday_treemap_hides_the_fixed_income_value_with_balances():
    fig = render_treemap_intraday(
        _holdings_frame(), has_weight=True, hide_balances=True
    )

    assert "2,050" not in _tile_text(fig)["Bank GIC"]
    assert "No intraday chg" in _tile_text(fig)["Bank GIC"]


def test_toggling_views_changes_only_the_leading_rows():
    frame = _holdings_frame()
    frame["timestamp"] = datetime(2026, 1, 5, tzinfo=timezone.utc)
    intraday = _tile_text(render_treemap_intraday(frame, has_weight=True))
    total = _leaf_text(render_treemap_positions(frame))

    # Securities keep weight and trade time in place; a GIC changes one row
    assert _rows(intraday["AAA"])[3:] == _rows(total["AAA"])[3:]
    assert _rows(intraday["Bank GIC"])[0] == _rows(total["Bank GIC"])[0]
    assert _rows(intraday["Bank GIC"])[2:] == _rows(total["Bank GIC"])[2:]


def test_market_page_tiles_have_no_weight_row():
    text = _tile_text(render_treemap_intraday(_frame(), group_cols=GROUPS))

    assert "Wt." not in text["AAA"]
    assert len(_rows(text["AAA"])) == 4


def test_intraday_treemap_nests_fixed_income_under_its_account():
    fig = render_treemap_intraday(
        _holdings_frame(), has_weight=True, group_cols=["account"]
    )

    parents = dict(zip(fig.data[0].labels, fig.data[0].parents))
    assert parents["Old GIC"].endswith("LIRA #2")
    assert parents["Bank GIC"].endswith("TFSA #1")


@pytest.mark.parametrize("group_cols", [None, ["account"]])
def test_intraday_and_total_return_treemaps_share_tiles_and_sizes(group_cols):
    frame = _holdings_frame()
    intraday = render_treemap_intraday(frame, has_weight=True, group_cols=group_cols)
    total = render_treemap_positions(frame, group_cols=group_cols)

    def sizes(fig, root):
        trace = fig.data[0]
        return {
            label: value
            for label, value in zip(trace.labels, trace.values)
            if label != root
        }

    assert sizes(intraday, "") == pytest.approx(sizes(total, "Holdings"))


def test_intraday_treemap_of_fixed_income_only_renders_its_tiles():
    frame = _holdings_frame().iloc[1:]

    text = _tile_text(render_treemap_intraday(frame, has_weight=True))

    assert "No intraday chg" in text["Bank GIC"]
    assert "No intraday chg" in text["Old GIC"]
