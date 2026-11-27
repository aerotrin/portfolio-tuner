import numpy as np
import pandas as pd
import pytest

from frontend.settings import GREEN, RED
from frontend.shared.styles import (
    FUNDAMENTALS_CONFIG,
    drop_empty_columns,
    PERFORMANCE_TABLE_CONFIG,
    POSITIONS_EQUITY_TABLE_CONFIG,
    POSITIONS_OPTION_TABLE_CONFIG,
    QUOTE_TABLE_CONFIG,
    _day_change_text,
    performance_table_styler,
    positions_table_styler,
    quote_table_styler,
)

STYLERS = [positions_table_styler, quote_table_styler, performance_table_styler]


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "close": [611.68, 1234.5, 45.1, 10.0],
            "currency": ["USD", "USD", "CAD", "CAD"],
            "change_percent": [-0.0414, 0.2297, 0.0, np.nan],
            "gain": [100.0, -50.0, 0.0, 5.0],
            "gain_pct": [0.1, -0.05, 0.0, 0.01],
            "rsi": [50.0, 50.0, 50.0, 50.0],
            "near_52wk_hi": False,
            "near_52wk_lo": False,
        },
        index=pd.Index(["DOWN", "UP", "FLAT", "PRE"]),
    )


def _rendered(df: pd.DataFrame, make=positions_table_styler) -> tuple[dict, dict]:
    """Display text and CSS per (row label, column) as the table shows them."""
    styler = make(df)
    styler._compute()
    body = styler._translate(True, True)["body"]
    props = styler.ctx
    text, css = {}, {}
    for i, (label, row) in enumerate(zip(df.index, body)):
        cells = [c for c in row if c["type"] == "td"]
        for j, (column, cell) in enumerate(zip(df.columns, cells)):
            text[label, column] = cell["display_value"]
            css[label, column] = ";".join(f"{k}:{v}" for k, v in props.get((i, j), []))
    return text, css


@pytest.mark.parametrize(
    "value, text",
    [(0.0414, "▲ 4.14%"), (-0.0414, "▼ 4.14%"), (0.0, "0.00%"), (np.nan, "—")],
)
def test_day_change_text(value, text):
    assert _day_change_text(value) == text


@pytest.mark.parametrize("make", STYLERS)
def test_price_shows_its_currency_and_day_shows_an_arrow(make):
    text, _ = _rendered(_frame(), make)

    assert text["DOWN", "close"] == "611.68 USD"
    assert text["UP", "close"] == "1,234.50 USD"
    assert text["FLAT", "close"] == "45.10 CAD"
    assert text["DOWN", "change_percent"] == "▼ 4.14%"
    assert text["UP", "change_percent"] == "▲ 22.97%"


@pytest.mark.parametrize("make", STYLERS)
def test_price_and_day_are_coloured_by_todays_move(make):
    _, css = _rendered(_frame(), make)

    for column in ("close", "change_percent"):
        assert RED in css["DOWN", column]
        assert GREEN in css["UP", column]
        assert css["FLAT", column] == ""
        assert css["PRE", column] == ""


def test_price_and_day_stay_numeric_underneath():
    df = _frame()

    data = positions_table_styler(df).data

    assert data["close"].dtype == float
    assert data["change_percent"].dtype == float


@pytest.mark.parametrize("make", STYLERS)
def test_price_without_a_currency_is_still_formatted(make):
    df = _frame()
    df["currency"] = [None, "USD", "CAD", "CAD"]

    text, _ = _rendered(df, make)

    assert text["DOWN", "close"] == "611.68"
    assert text["UP", "close"] == "1,234.50 USD"


@pytest.mark.parametrize("config", [QUOTE_TABLE_CONFIG, PERFORMANCE_TABLE_CONFIG])
def test_quote_and_performance_tables_show_price_day_signal_together(config):
    columns = list(config)

    assert "currency" not in columns and "change" not in columns
    start = columns.index("close")
    assert columns[start : start + 3] == ["close", "change_percent", "signal"]


def test_frame_without_quote_columns_still_styles():
    fixed_income = _frame()[["gain", "gain_pct"]]

    text, _ = _rendered(fixed_income)

    assert set(column for _, column in text) == {"gain", "gain_pct"}


def test_equity_table_leads_with_price_day_signal_and_has_no_currency_column():
    columns = list(POSITIONS_EQUITY_TABLE_CONFIG)

    assert "currency" not in columns
    start = columns.index("close")
    assert columns[start : start + 4] == [
        "close",
        "change_percent",
        "signal",
        "relative_volume",
    ]
    assert columns.index("relative_volume") < columns.index("intraday_change")
    assert columns.index("weight") < columns.index("open_qty")


def test_option_table_leads_with_the_underlying():
    columns = list(POSITIONS_OPTION_TABLE_CONFIG)

    start = columns.index("sparkline")
    assert columns[start + 1 : start + 3] == ["close", "change_percent"]


# ── Fundamentals columns ────────────────────────────────────────────────────


def test_quote_table_shows_all_fundamentals_after_dollar_volume() -> None:
    order = list(QUOTE_TABLE_CONFIG)
    start = order.index("dollar_volume") + 1

    assert order[start : start + 6] == list(FUNDAMENTALS_CONFIG)
    assert order[start + 6] == "previousClose"


def test_holdings_and_performance_tables_show_pe_and_yield() -> None:
    equity = list(POSITIONS_EQUITY_TABLE_CONFIG)
    at = equity.index("relative_volume")
    assert equity[at + 1 : at + 4] == [
        "trailing_pe",
        "dividend_yield",
        "intraday_change",
    ]

    performance = list(PERFORMANCE_TABLE_CONFIG)
    at = performance.index("max_drawdown_date")
    assert performance[at + 1 : at + 4] == ["trailing_pe", "dividend_yield", "exchange"]

    assert "trailing_pe" not in POSITIONS_OPTION_TABLE_CONFIG


def test_fundamentals_columns_with_no_values_are_left_out() -> None:
    funds = pd.DataFrame(
        {
            "symbol": ["XIU", "SPY"],
            "name": [None, None],
            "market_cap": [None, None],
            "net_assets": [2.3e10, np.nan],
            "trailing_pe": [18.0, 22.8],
        }
    )

    order = drop_empty_columns(QUOTE_TABLE_CONFIG, funds)

    assert "market_cap" not in order
    # Missing from the frame altogether
    assert "forward_pe" not in order
    assert "net_assets" in order
    assert "trailing_pe" in order
    # Only fundamentals are dropped
    assert "name" in order
    assert "volume" in order


def test_quote_table_shows_the_52_week_range_after_the_day_range() -> None:
    order = list(QUOTE_TABLE_CONFIG)
    at = order.index("high")

    assert order[at : at + 5] == ["high", "low", "high_52w", "low_52w", "volatility"]
