from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from frontend.settings import HEIGHT_PRICE_CHART_PANELS
from frontend.shared.constants import MISSING_VALUE
from frontend.widgets.price_chart import (
    _fmt_range,
    _fundamental_cards,
    parse_ma_periods,
    resolve_symbol_click,
    symbol_from_selection,
)
from frontend.widgets.price_chart_figure import (
    CHART_CANDLES,
    CHART_LINE,
    PANEL_MACD,
    PANEL_RSI,
    PANEL_VOLUME,
    build_price_chart_figure,
    chart_frame,
    compute_rangebreaks,
    figure_height,
    moving_average_columns,
    panel_layout,
    slice_to_range,
)

EXTRA_PANELS = [PANEL_VOLUME, PANEL_RSI, PANEL_MACD]
PANEL_SUBSETS = [
    list(subset)
    for size in range(len(EXTRA_PANELS) + 1)
    for subset in combinations(EXTRA_PANELS, size)
]


def _payload(n: int = 60) -> dict:
    dates = pd.bdate_range("2024-01-02", periods=n)
    close = [100.0 + i for i in range(n)]
    ma20 = [None] * 19 + [c - 5 for c in close[19:]]
    return {
        "summary": {},
        "ranges": [],
        "series": {
            "dates": [d.strftime("%Y-%m-%d") for d in dates],
            "open": [c - 1 for c in close],
            "high": [c + 2 for c in close],
            "low": [c - 2 for c in close],
            "close": close,
            "volume": [1000.0] * n,
            "moving_averages": [
                {"kind": "sma", "period": 20, "values": ma20},
                {"kind": "sma", "period": 200, "values": [None] * n},
            ],
            "bb_middle": ma20,
            "bb_upper": [None if v is None else v + 3 for v in ma20],
            "bb_lower": [None if v is None else v - 3 for v in ma20],
            "rsi": [None] * 14 + [55.0] * (n - 14),
            "macd": [None] * 25 + [1.0] * (n - 25),
            "macd_signal": [None] * 33 + [0.5] * (n - 33),
            "macd_histogram": [None] * 33 + [0.5, -0.5] * ((n - 33) // 2) + [0.5],
        },
    }


def _frame(n: int = 60) -> pd.DataFrame:
    return chart_frame(_payload(n))


def _trace_types(fig) -> list[str]:
    return [trace.type for trace in fig.data]


# ── Payload helpers ─────────────────────────────────────────────────────────


def test_chart_frame_is_date_indexed_with_nan_for_nulls() -> None:
    frame = _frame()

    assert isinstance(frame.index, pd.DatetimeIndex)
    assert len(frame) == 60
    assert np.isnan(frame["ma_20"].iloc[0])
    assert frame["ma_20"].iloc[19] == pytest.approx(114.0)
    assert frame["ma_200"].isna().all()


def test_chart_frame_handles_an_empty_payload() -> None:
    assert chart_frame({"series": {}}).empty


def test_moving_average_columns_are_labelled_by_kind_and_period() -> None:
    assert moving_average_columns(_payload()) == [
        ("ma_20", "SMA 20"),
        ("ma_200", "SMA 200"),
    ]


def test_slice_to_range_keeps_the_last_sessions() -> None:
    frame = _frame()

    assert len(slice_to_range(frame, 5)) == 5
    assert slice_to_range(frame, 5).index[-1] == frame.index[-1]
    assert len(slice_to_range(frame, 500)) == 60
    assert slice_to_range(frame, 0).empty


# ── Rangebreaks ─────────────────────────────────────────────────────────────


def test_rangebreaks_hide_weekends_and_missing_weekdays() -> None:
    dates = pd.bdate_range("2024-01-02", periods=10).delete(3)

    breaks = compute_rangebreaks(dates)

    assert breaks[0] == {"bounds": ["sat", "mon"]}
    assert breaks[1] == {"values": ["2024-01-05"]}


def test_rangebreaks_without_holidays_only_hide_weekends() -> None:
    assert compute_rangebreaks(pd.bdate_range("2024-01-02", periods=10)) == [
        {"bounds": ["sat", "mon"]}
    ]


def test_rangebreaks_are_skipped_for_weekend_traded_symbols() -> None:
    assert compute_rangebreaks(pd.date_range("2024-01-01", periods=10)) == []


# ── Panels ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("panels", PANEL_SUBSETS)
def test_panel_layout_stacks_without_overlap(panels) -> None:
    layout = panel_layout(panels)

    assert [p.name for p in layout] == ["price", *panels]
    assert layout[0].axis == "y" and layout[0].layout_key == "yaxis"
    assert layout[0].domain[1] == pytest.approx(1.0)
    assert layout[-1].domain[0] == pytest.approx(0.0)
    for upper, lower in zip(layout, layout[1:]):
        assert lower.domain[1] < upper.domain[0]


def test_price_panel_keeps_its_height_as_panels_are_added() -> None:
    for panels in PANEL_SUBSETS:
        low, high = panel_layout(panels)[0].domain
        plot_height = figure_height(panels) - figure_height([]) + 340
        assert (high - low) * plot_height == pytest.approx(
            HEIGHT_PRICE_CHART_PANELS["price"]
        )


def test_panel_layout_ignores_request_order() -> None:
    names = [p.name for p in panel_layout([PANEL_MACD, PANEL_VOLUME])]

    assert names == ["price", PANEL_VOLUME, PANEL_MACD]


# ── Figure ──────────────────────────────────────────────────────────────────


def test_candles_only_figure() -> None:
    fig = build_price_chart_figure(_frame())

    assert _trace_types(fig) == ["candlestick"]
    assert fig.layout.xaxis.rangeslider.visible is False
    assert fig.layout.hovermode == "x unified"
    assert fig.layout.hoversubplots == "axis"


def test_line_chart_replaces_candles() -> None:
    fig = build_price_chart_figure(_frame(), chart_type=CHART_LINE)

    assert _trace_types(fig) == ["scatter"]
    assert fig.data[0].name == "Close"


@pytest.mark.parametrize("panels", PANEL_SUBSETS)
def test_every_trace_shares_one_x_axis_and_sits_on_its_panel(panels) -> None:
    fig = build_price_chart_figure(
        _frame(),
        moving_averages=[("ma_20", "SMA 20")],
        chart_type=CHART_CANDLES,
        show_bollinger=True,
        panels=panels,
    )
    axes = {p.name: p.axis for p in panel_layout(panels)}
    by_name = {trace.name: trace for trace in fig.data}

    assert all(trace.xaxis == "x" for trace in fig.data)
    assert by_name["OHLC"].yaxis == "y"
    assert by_name["SMA 20"].yaxis == "y"
    assert by_name["Bollinger (20, 2)"].yaxis == "y"
    assert by_name["Bollinger (20, 2)"].fill == "tonexty"
    assert ("Volume" in by_name) == (PANEL_VOLUME in panels)
    assert ("RSI 14" in by_name) == (PANEL_RSI in panels)
    assert ("MACD" in by_name) == (PANEL_MACD in panels)
    if PANEL_VOLUME in panels:
        assert by_name["Volume"].type == "bar"
        assert by_name["Volume"].yaxis == axes[PANEL_VOLUME]
    if PANEL_RSI in panels:
        assert by_name["RSI 14"].yaxis == axes[PANEL_RSI]
    if PANEL_MACD in panels:
        for name in ("MACD", "Signal", "Histogram"):
            assert by_name[name].yaxis == axes[PANEL_MACD]
    assert fig.layout.xaxis.anchor == panel_layout(panels)[-1].axis
    assert fig.layout.height == figure_height(panels)


def test_rsi_panel_has_fixed_range_and_shaded_band() -> None:
    fig = build_price_chart_figure(_frame(), panels=[PANEL_RSI])

    assert tuple(fig.layout.yaxis2.range) == (0, 100)
    band = [s for s in fig.layout.shapes if s.type == "rect"]
    assert len(band) == 1
    assert (band[0].y0, band[0].y1, band[0].yref) == (30, 70, "y2")


def test_moving_average_without_values_in_window_is_omitted() -> None:
    fig = build_price_chart_figure(
        _frame(), moving_averages=[("ma_20", "SMA 20"), ("ma_200", "SMA 200")]
    )

    assert [t.name for t in fig.data] == ["OHLC", "SMA 20"]


def test_bollinger_is_omitted_when_the_window_has_no_band() -> None:
    fig = build_price_chart_figure(_frame().head(10), show_bollinger=True)

    assert _trace_types(fig) == ["candlestick"]


def test_price_tags_use_the_price_axis_and_skip_missing_values() -> None:
    fig = build_price_chart_figure(
        _frame(),
        moving_averages=[("ma_20", "SMA 20"), ("ma_200", "SMA 200")],
        panels=[PANEL_VOLUME],
        show_price_tags=True,
    )

    tags = [a for a in fig.layout.annotations if a.yref == "y"]
    assert sorted(a.text for a in tags) == ["154.00", "159.00"]
    assert all(a.xref == "paper" and a.x == 1 for a in tags)
    assert any(s.type == "line" and s.y0 == 159.0 for s in fig.layout.shapes)


def test_no_price_tags_by_default() -> None:
    fig = build_price_chart_figure(_frame(), moving_averages=[("ma_20", "SMA 20")])

    assert not [a for a in fig.layout.annotations if a.yref == "y"]


def test_volume_bars_follow_candle_direction() -> None:
    frame = _frame()
    frame.iloc[-1, frame.columns.get_loc("open")] = frame["close"].iloc[-1] + 5

    fig = build_price_chart_figure(frame, panels=[PANEL_VOLUME])

    colors = fig.data[-1].marker.color
    assert colors[0] != colors[-1]


# ── Dialog helpers ──────────────────────────────────────────────────────────


def _state(cells: list, rows: list | None = None) -> dict:
    return {"selection": {"rows": rows or [], "columns": [], "cells": cells}}


def test_symbol_from_selection_returns_the_clicked_symbol() -> None:
    state = _state([(1, "symbol")], rows=[0])

    assert symbol_from_selection(state, ["AAA", "BBB", "CCC"]) == "BBB"


def test_symbol_from_selection_ignores_other_columns_and_bad_rows() -> None:
    symbols = ["AAA", "BBB"]

    assert symbol_from_selection(_state([(0, "name")]), symbols) is None
    assert symbol_from_selection(_state([(5, "symbol")]), symbols) is None
    assert symbol_from_selection(_state([]), symbols) is None
    assert symbol_from_selection(None, symbols) is None
    assert symbol_from_selection({}, symbols) is None


def test_symbol_from_selection_maps_an_option_row_to_its_underlying() -> None:
    state = _state([[0, "option_osi"]])

    assert symbol_from_selection(state, ["AAPL"], ("option_osi",)) == "AAPL"
    assert symbol_from_selection(state, ["AAPL"]) is None


SYMBOLS = ["AAA", "BBB", "CCC"]


def test_click_on_a_symbol_opens_it_and_is_remembered() -> None:
    symbol, seen = resolve_symbol_click(_state([(1, "symbol")], [2, 0]), None, SYMBOLS)

    assert symbol == "BBB"
    assert seen == {"cell": [1, "symbol"], "rows": [0, 2]}


def test_same_symbol_can_be_clicked_again() -> None:
    seen = {"cell": [1, "symbol"], "rows": [0]}

    symbol, _ = resolve_symbol_click(_state([(1, "symbol")], [0]), seen, SYMBOLS)

    assert symbol == "BBB"


def test_ticking_a_row_does_not_reopen_the_last_clicked_symbol() -> None:
    seen = {"cell": [1, "symbol"], "rows": [0]}

    symbol, now = resolve_symbol_click(_state([(1, "symbol")], [0, 2]), seen, SYMBOLS)

    assert symbol is None
    assert now == {"cell": [1, "symbol"], "rows": [0, 2]}


def test_click_on_a_different_symbol_opens_it_even_after_row_changes() -> None:
    seen = {"cell": [1, "symbol"], "rows": [0]}

    symbol, _ = resolve_symbol_click(_state([(2, "symbol")], [0, 2]), seen, SYMBOLS)

    assert symbol == "CCC"


def test_stale_table_resending_the_handled_cell_does_not_reopen() -> None:
    seen = {"cell": [1, "symbol"], "rows": [0]}
    same_rows = _state([(1, "symbol")], [0])
    new_rows = _state([(1, "symbol")], [0, 2])

    assert resolve_symbol_click(same_rows, seen, SYMBOLS, stale=True)[0] is None
    assert resolve_symbol_click(new_rows, seen, SYMBOLS, stale=True)[0] is None


def test_stale_table_click_on_a_different_symbol_opens_it() -> None:
    seen = {"cell": [1, "symbol"], "rows": [0]}

    symbol, now = resolve_symbol_click(
        _state([(2, "symbol")], [0]), seen, SYMBOLS, stale=True
    )

    assert symbol == "CCC"
    assert now == {"cell": [2, "symbol"], "rows": [0]}


def test_click_on_another_column_forgets_the_last_symbol() -> None:
    seen = {"cell": [1, "symbol"], "rows": [0]}

    assert resolve_symbol_click(_state([(1, "name")], [0]), seen, SYMBOLS) == (
        None,
        None,
    )
    assert resolve_symbol_click(_state([], [0]), seen, SYMBOLS) == (None, None)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([20, 50, 200], (20, 50, 200)),
        (["30", 20, " 9 "], (9, 20, 30)),
        ([50, "50", 50], (50,)),
        (["abc", 1, 251, 0, "7.5"], ()),
        ([2, 3, 4, 5, 6, 7], (2, 3, 4, 5, 6)),
        ([], ()),
    ],
)
def test_parse_ma_periods(values, expected) -> None:
    assert parse_ma_periods(values) == expected


# ── Reset to defaults ───────────────────────────────────────────────────────


def test_reset_restores_the_default_view_and_keeps_the_symbol() -> None:
    import streamlit as st

    from frontend.settings import PRICE_CHART_DEFAULTS
    from frontend.widgets import price_chart as pc

    st.session_state.clear()
    st.session_state[pc.SYMBOL_KEY] = "NVDA"
    st.session_state[pc.PREFS_KEY] = {"range": "5D", "type": "Line", "show": []}
    st.session_state["price_chart_range"] = "5D"
    st.session_state["price_chart_show"] = ["MACD"]

    pc._reset_prefs()

    assert st.session_state[pc.PREFS_KEY] == PRICE_CHART_DEFAULTS
    for pref, key in pc.PREF_WIDGET_KEYS.items():
        assert st.session_state[key] == PRICE_CHART_DEFAULTS[pref]
    assert st.session_state[pc.SYMBOL_KEY] == "NVDA"
    st.session_state.clear()


def test_reset_does_not_share_lists_with_the_settings() -> None:
    import streamlit as st

    from frontend.settings import PRICE_CHART_DEFAULTS
    from frontend.widgets import price_chart as pc

    st.session_state.clear()
    pc._reset_prefs()
    st.session_state[pc.PREFS_KEY]["show"].append("MACD")
    st.session_state[pc.PREFS_KEY]["ma_periods"].append(7)

    assert "MACD" not in PRICE_CHART_DEFAULTS["show"]
    assert 7 not in PRICE_CHART_DEFAULTS["ma_periods"]
    st.session_state.clear()


# ── KPI row ─────────────────────────────────────────────────────────────────


def test_range_reads_low_to_high() -> None:
    assert _fmt_range(1234.5, 2345.678) == "1,234.50 – 2,345.68"


@pytest.mark.parametrize("low, high", [(None, 2.0), (1.0, None), (float("nan"), 2.0)])
def test_range_with_a_missing_end_is_blank(low, high) -> None:
    assert _fmt_range(low, high) == MISSING_VALUE


def test_fundamental_cards_follow_the_table_order() -> None:
    cards = _fundamental_cards(
        {
            "market_cap": 2.5e9,
            "trailing_pe": 20.04,
            "forward_pe": 12.5,
            "eps": 2.5,
            "dividend_yield": 0.021,
        }
    )

    assert [label for label, _ in cards] == [
        "Mkt cap",
        "P/E",
        "Fwd P/E",
        "EPS",
        "Div yield",
    ]
    assert dict(cards)["P/E"] == "20.0"
    assert dict(cards)["Div yield"] == "2.10%"


def test_fundamental_cards_for_a_fund_show_net_assets_and_skip_blanks() -> None:
    cards = _fundamental_cards(
        {"market_cap": None, "net_assets": 4.0e10, "dividend_yield": 0.015}
    )

    assert [label for label, _ in cards] == ["Net assets", "Div yield"]


def test_fundamental_cards_are_empty_without_fundamentals() -> None:
    assert _fundamental_cards({}) == []
