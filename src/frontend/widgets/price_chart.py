from functools import partial
from typing import Any, Mapping, Sequence

import pandas as pd
import requests
import streamlit as st

from frontend.services.streamlit_data import load_price_chart
from frontend.shared.time import format_last_trade
from frontend.widgets.price_chart_figure import (
    CHART_CANDLES,
    CHART_LINE,
    PANEL_MACD,
    PANEL_RSI,
    PANEL_VOLUME,
    build_price_chart_figure,
    chart_frame,
    moving_average_columns,
    slice_to_range,
)
from frontend.widgets.treemaps import compact_number
from frontend.settings import PRICE_CHART_DEFAULTS, PRICE_CHART_MA_PERIOD_OPTIONS
from frontend.shared.constants import (
    DAY_CHANGE_HELP,
    MISSING_VALUE,
    PRICE_CHART_MA_MAX_COUNT,
    PRICE_CHART_MA_MAX_PERIOD,
    PRICE_CHART_MA_MIN_PERIOD,
    PRICE_CHART_RANGES,
)

OPEN_KEY = "price_chart_open"
PREFS_KEY = "price_chart_prefs"
SYMBOL_KEY = "price_chart_symbol"
SYMBOL_CLICK_COLUMNS = ("symbol",)

CHART_TYPES = {"Candles": CHART_CANDLES, "Line": CHART_LINE}
SHOW_MA = "Moving averages"
SHOW_BOLLINGER = "Bollinger bands"
SHOW_VOLUME = "Volume"
SHOW_RSI = "RSI"
SHOW_MACD = "MACD"
SHOW_TAGS = "Price tags"
SHOW_OPTIONS = (SHOW_MA, SHOW_BOLLINGER, SHOW_VOLUME, SHOW_RSI, SHOW_MACD, SHOW_TAGS)
SHOW_PANELS = {SHOW_VOLUME: PANEL_VOLUME, SHOW_RSI: PANEL_RSI, SHOW_MACD: PANEL_MACD}
MA_TYPES = ("SMA", "EMA")


def symbol_from_selection(
    state: Mapping[str, Any] | None,
    row_symbols: Sequence[str],
    click_columns: Sequence[str] = SYMBOL_CLICK_COLUMNS,
) -> str | None:
    """Symbol of the clicked cell, when the click landed on a symbol column.

    Row positions refer to the frame given to st.dataframe, so they stay
    correct after the user sorts the table in the browser.
    """
    cells = ((state or {}).get("selection") or {}).get("cells") or []
    for cell in cells:
        row, column = cell[0], cell[1]
        if column in click_columns and 0 <= row < len(row_symbols):
            return row_symbols[row] or None
    return None


def parse_ma_periods(values: Sequence[Any]) -> tuple[int, ...]:
    """Whole-number periods within bounds, deduplicated and sorted; typed
    entries that are not valid periods are dropped."""
    periods = set()
    for value in values:
        try:
            period = int(str(value).strip())
        except ValueError:
            continue
        if PRICE_CHART_MA_MIN_PERIOD <= period <= PRICE_CHART_MA_MAX_PERIOD:
            periods.add(period)
    return tuple(sorted(periods)[:PRICE_CHART_MA_MAX_COUNT])


def symbol_table_key(base_key: str) -> str:
    """Widget key of a symbol-click table.

    The key changes after every handled symbol click, which remounts the
    table with the clicked cell deselected, so the same symbol can be clicked
    again.
    """
    return f"{base_key}-c{st.session_state.get(f'{base_key}-clicks', 0)}"


def resolve_symbol_click(
    state: Mapping[str, Any] | None,
    seen: Mapping[str, Any] | None,
    row_symbols: Sequence[str],
    click_columns: Sequence[str] = SYMBOL_CLICK_COLUMNS,
    stale: bool = False,
) -> tuple[str | None, dict[str, Any] | None]:
    """Decide whether a table selection event is a new click on a symbol.

    A grid keeps its clicked cell selected, so the cell comes back with every
    later event from that grid. `seen` is the cell and ticked rows of the last
    handled click. The same cell is a leftover, not a click, when the rows
    changed (a checkbox tick) or when the event is `stale`: sent by a table
    that has already been replaced but is still on screen because the rerun
    that replaces it was interrupted.

    Returns the symbol to open (or None) and the value to remember as `seen`;
    that is None when no symbol cell is selected.
    """
    selection = (state or {}).get("selection") or {}
    rows = sorted(selection.get("rows") or [])
    symbol = symbol_from_selection(state, row_symbols, click_columns)
    if symbol is None:
        return None, None
    cell = list((selection.get("cells") or [])[0])
    now = {"cell": cell, "rows": rows}
    if seen and seen["cell"] == cell and (stale or seen["rows"] != rows):
        return None, now
    return symbol, now


def _row_selection(rows: Sequence[int]) -> dict[str, Any]:
    return {"selection": {"rows": list(rows), "columns": [], "cells": []}}


def open_price_chart_from_click(
    base_key: str,
    table_key: str,
    row_symbols: Sequence[str],
    click_columns: Sequence[str] = SYMBOL_CLICK_COLUMNS,
) -> None:
    """`on_select` callback for a table with "single-cell" selection.

    `table_key` is the key of the table that sent the event. A new click on
    a symbol cell opens the chart. Whenever the sending table holds a symbol
    cell or is stale, the table moves to its next key with the ticked rows
    carried over, so row selections survive and no leftover cell remains.
    """
    state = st.session_state.get(table_key)
    if state is None:
        return
    seen_key = f"{base_key}-seen"
    stale = table_key != symbol_table_key(base_key)
    symbol, seen = resolve_symbol_click(
        state, st.session_state.get(seen_key), row_symbols, click_columns, stale
    )
    if seen is None and not stale:
        st.session_state[seen_key] = None
        return
    if seen is not None:
        st.session_state[seen_key] = seen
    rows = sorted((state.get("selection") or {}).get("rows") or [])
    st.session_state[f"{base_key}-clicks"] = (
        st.session_state.get(f"{base_key}-clicks", 0) + 1
    )
    # Session state serves code that reads the selection before the table is
    # drawn; the default (see symbol_click_kwargs) is what the browser applies,
    # and unlike a session-state value it survives an interrupted rerun.
    new_key = symbol_table_key(base_key)
    st.session_state[f"{base_key}-carry"] = {"key": new_key, "rows": rows}
    if rows:
        st.session_state[new_key] = _row_selection(rows)
    if symbol is None:
        return
    symbols = list(dict.fromkeys(s for s in row_symbols if s))
    st.session_state[OPEN_KEY] = {"symbols": symbols}
    st.session_state[SYMBOL_KEY] = symbol


def symbol_click_kwargs(
    base_key: str,
    row_symbols: Sequence[str],
    *,
    click_columns: Sequence[str] = SYMBOL_CLICK_COLUMNS,
    row_selection: str | None = None,
) -> dict[str, Any]:
    """st.dataframe arguments that open the price chart on a symbol click.

    The table's widget key is `symbol_table_key(base_key)`.
    """
    modes = [row_selection, "single-cell"] if row_selection else "single-cell"
    table_key = symbol_table_key(base_key)
    kwargs: dict[str, Any] = dict(
        key=table_key,
        on_select=partial(
            open_price_chart_from_click,
            base_key,
            table_key,
            tuple(row_symbols),
            tuple(click_columns),
        ),
        selection_mode=modes,
    )
    carry = st.session_state.get(f"{base_key}-carry")
    if carry and carry["key"] == table_key and carry["rows"]:
        kwargs["selection_default"] = _row_selection(carry["rows"])
    return kwargs


def _close_price_chart() -> None:
    st.session_state.pop(OPEN_KEY, None)


def _fmt(value: float | None, spec: str) -> str:
    return MISSING_VALUE if value is None or pd.isna(value) else format(value, spec)


def _compact(value: float | None) -> str:
    return (
        MISSING_VALUE
        if value is None or pd.isna(value) or not value
        else compact_number(value)
    )


PREF_WIDGET_KEYS = {
    "range": "price_chart_range",
    "type": "price_chart_type",
    "show": "price_chart_show",
    "ma_type": "price_chart_ma_type",
    "ma_periods": "price_chart_ma_periods",
}


def _seed_widgets(prefs: dict[str, Any]) -> None:
    """Push the remembered choices into the dialog's widgets.

    Assigning through session state makes the browser adopt the values; a
    reopened dialog otherwise mounts its controls with nothing selected.
    """
    for pref, key in PREF_WIDGET_KEYS.items():
        st.session_state[key] = prefs[pref]


def _render_kpis(summary: dict[str, Any], range_key: str, change: dict[str, Any]):
    last = summary.get("last_price")
    change_1d = summary.get("change_1d")
    pct_1d = summary.get("change_percent_1d")
    with st.container(border=True, horizontal=True):
        st.metric(
            "Last",
            _fmt(last, ",.2f"),
            (
                None
                if change_1d is None
                else f"{change_1d:+,.2f} ({_fmt(pct_1d, '+.2%')})"
            ),
            help=DAY_CHANGE_HELP,
        )
        st.metric(
            f"{range_key} change",
            _fmt(change.get("change_percent"), "+.2%"),
            (
                _fmt(change.get("change"), "+,.2f")
                if change.get("change") is not None
                else None
            ),
            help="Change over the selected range, measured from the close "
            "before its first session",
        )
        st.metric("52-week high", _fmt(summary.get("high_52w"), ",.2f"))
        st.metric("52-week low", _fmt(summary.get("low_52w"), ",.2f"))
        st.metric("Volume", _compact(summary.get("volume")))
        st.metric("Market cap", _compact(summary.get("market_cap")))


@st.dialog(
    "Daily price chart",
    width="large",
    icon=":material/candlestick_chart:",
    on_dismiss=_close_price_chart,
)
def _price_chart_dialog(symbols: list[str]) -> None:
    prefs = st.session_state.setdefault(PREFS_KEY, dict(PRICE_CHART_DEFAULTS))
    if st.session_state.get(SYMBOL_KEY) not in symbols:
        st.session_state[SYMBOL_KEY] = symbols[0]
    if any(key not in st.session_state for key in PREF_WIDGET_KEYS.values()):
        _seed_widgets(prefs)

    with st.container(horizontal=True, vertical_alignment="bottom"):
        symbol = st.selectbox("Symbol", symbols, key=SYMBOL_KEY, width=200)
        range_key = st.segmented_control(
            "Range",
            PRICE_CHART_RANGES,
            key="price_chart_range",
            required=True,
            width="content",
        )
    with st.container(horizontal=True, vertical_alignment="bottom"):
        chart_type = st.segmented_control(
            "Chart",
            list(CHART_TYPES),
            key="price_chart_type",
            required=True,
            width="content",
        )
        show = st.pills(
            "Show",
            SHOW_OPTIONS,
            selection_mode="multi",
            key="price_chart_show",
            width="content",
        )
        with st.popover(":material/settings:", type="tertiary"):
            ma_type = st.segmented_control(
                "Moving average type",
                MA_TYPES,
                key="price_chart_ma_type",
                required=True,
            )
            raw_periods = st.multiselect(
                "Periods (days)",
                PRICE_CHART_MA_PERIOD_OPTIONS,
                key="price_chart_ma_periods",
                accept_new_options=True,
                max_selections=PRICE_CHART_MA_MAX_COUNT,
                help=f"Up to {PRICE_CHART_MA_MAX_COUNT} periods between "
                f"{PRICE_CHART_MA_MIN_PERIOD} and {PRICE_CHART_MA_MAX_PERIOD} days. "
                "Type a number to add your own.",
            )
    periods = parse_ma_periods(raw_periods)
    prefs.update(
        range=range_key,
        type=chart_type,
        show=list(show),
        ma_type=ma_type,
        ma_periods=list(periods),
    )

    try:
        payload = load_price_chart(symbol, ma_type.lower(), periods)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            st.info(f"No price history is stored for {symbol} yet.")
        else:
            st.error(f"Failed to load the price chart for {symbol}.")
        return
    except requests.RequestException:
        st.error(f"Failed to load the price chart for {symbol}.")
        return

    summary = payload["summary"]
    ranges = {r["key"]: r for r in payload["ranges"]}
    selected = ranges[range_key]
    details = [summary.get("name"), summary.get("exchange"), summary.get("currency")]
    st.caption(" · ".join(d for d in details if d))
    _render_kpis(summary, range_key, selected)

    frame = chart_frame(payload)
    if len(frame) < 2:
        st.info("Not enough price history to draw a chart yet.")
        return
    view = slice_to_range(frame, selected["sessions"])
    averages = moving_average_columns(payload) if SHOW_MA in show and periods else []
    fig = build_price_chart_figure(
        view,
        moving_averages=averages,
        chart_type=CHART_TYPES[chart_type],
        show_bollinger=SHOW_BOLLINGER in show,
        panels=[SHOW_PANELS[s] for s in show if s in SHOW_PANELS],
        show_price_tags=SHOW_TAGS in show,
        theme=st.context.theme.type or "light",
    )
    st.plotly_chart(fig, key="price_chart_figure", config={"displayModeBar": False})

    notes = [
        f"Last trade: {format_last_trade(summary.get('last_trade'), st.context.timezone)}"
    ]
    hidden = [label for column, label in averages if view[column].notna().sum() == 0]
    if hidden:
        notes.append(f"{', '.join(hidden)}: not enough stored history for this range")
    st.caption(" · ".join(notes))


def render_open_price_chart() -> None:
    """Show the price chart while it is flagged open.

    Called on every run: a full rerun (the app refresh timer) closes a dialog
    that is not invoked again, so the flag stays set until it is dismissed.
    """
    request = st.session_state.get(OPEN_KEY)
    if not request or not request.get("symbols"):
        return
    if not request.get("seeded"):
        _seed_widgets(
            st.session_state.setdefault(PREFS_KEY, dict(PRICE_CHART_DEFAULTS))
        )
        request["seeded"] = True
    _price_chart_dialog(request["symbols"])
