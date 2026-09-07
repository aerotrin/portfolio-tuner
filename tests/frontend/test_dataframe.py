import numpy as np
import pandas as pd
import pytest

from frontend.services.streamlit_data import PortfolioData, SecurityData
from frontend.shared.dataframe import build_holdings_view, compute_correlation_matrix
from frontend.shared.settings import TRADING_DAYS_PER_YEAR


def _closes(data: dict[str, list[float]], periods: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="B")
    return pd.DataFrame(data, index=index)


def test_perfectly_correlated_and_inverse_pairs():
    n = 100
    rng = np.random.default_rng(42)
    r = rng.normal(0, 0.01, n)
    # Daily returns r, 2r, and -r give exact pairwise correlations of +1 and -1.
    closes = _closes(
        {
            "AAA": (100 * np.cumprod(1 + r)).tolist(),
            "BBB": (100 * np.cumprod(1 + 2 * r)).tolist(),
            "CCC": (100 * np.cumprod(1 - r)).tolist(),
        },
        n,
    )

    corr = compute_correlation_matrix(closes)

    assert corr.loc["AAA", "BBB"] == pytest.approx(1.0)
    assert corr.loc["AAA", "CCC"] == pytest.approx(-1.0)


def test_symbols_filter_restricts_columns_and_ignores_unknown():
    n = 50
    rng = np.random.default_rng(42)
    closes = _closes(
        {s: (100 + rng.standard_normal(n).cumsum()).tolist() for s in "ABC"}, n
    )

    corr = compute_correlation_matrix(closes, symbols=["A", "B", "ZZZ"])

    assert sorted(corr.columns) == ["A", "B"]
    assert sorted(corr.index) == ["A", "B"]


def test_only_trailing_window_used():
    extra = 100
    n = TRADING_DAYS_PER_YEAR + extra
    rng = np.random.default_rng(7)
    x = 100 + rng.standard_normal(n).cumsum()
    # Inside the trailing window Y moves with X; before it, Y moves against X.
    y = np.concatenate([-x[:extra] + 300, x[extra:]])
    closes = _closes({"X": x.tolist(), "Y": y.tolist()}, n)

    corr = compute_correlation_matrix(closes)

    assert corr.loc["X", "Y"] == pytest.approx(1.0)


def test_constant_price_column_dropped():
    n = 50
    rng = np.random.default_rng(1)
    closes = _closes(
        {
            "A": (100 + rng.standard_normal(n).cumsum()).tolist(),
            "B": (100 + rng.standard_normal(n).cumsum()).tolist(),
            "FLAT": [100.0] * n,
        },
        n,
    )

    corr = compute_correlation_matrix(closes)

    assert "FLAT" not in corr.columns
    assert "FLAT" not in corr.index
    assert sorted(corr.columns) == ["A", "B"]


def test_interior_nans_forward_filled():
    n = 60
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.01, n)
    a = 100 * np.cumprod(1 + r)
    a[10:15] = np.nan
    closes = _closes({"A": a.tolist(), "B": (100 * np.cumprod(1 + 2 * r)).tolist()}, n)

    corr = compute_correlation_matrix(closes)

    # A stays in the matrix (ffill bridges the gap) and remains strongly correlated.
    assert not np.isnan(corr.loc["A", "B"])
    assert corr.loc["A", "B"] > 0.8


# ---------------------------------------------------------------------------
# build_holdings_view
# ---------------------------------------------------------------------------

_OSI = "AAPL 250117C00100000"


def _indicator_records(symbol: str, closes: list[float]) -> list[dict]:
    dates = pd.date_range("2025-01-01", periods=len(closes), freq="B")
    return [
        {
            "symbol": symbol,
            "date": d.isoformat(),
            "close": c,
            "close_norm": c / closes[0],
            "daily_return": 0.0,
            "ema12": c,
            "ema26": c,
            "ema100": c,
            "macd_12_26": 0.0,
            "macd_signal_9": 0.0,
            "macd_histogram": 1.0,
            "rsi": 55.0,
            "rsi_signal_5": 55.0,
        }
        for d, c in zip(dates, closes)
    ]


def _mixed_portfolio(correlation_entries: list[dict] | None) -> PortfolioData:
    """Portfolio with a stock and an OSI-keyed call option on the same underlying."""

    def _holding(category: str, key_fields: dict) -> dict:
        return {
            "name": "Apple",
            "exchange": "TEST",
            "close": 110.0,
            "currency": "CAD",
            "change_percent": 0.01,
            "timestamp": "2025-01-10T16:00:00",
            **key_fields,
            "holding_category": category,
        }

    holdings = {
        "AAPL": _holding(
            "Equity",
            {"symbol": "AAPL", "open_qty": 10, "weight": 0.5, "market_value": 1100.0},
        ),
        _OSI: _holding(
            "Call Option",
            {"symbol": "AAPL", "open_qty": 1, "weight": 0.4, "market_value": 1000.0},
        ),
    }
    metrics = {
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple",
            "return1Y": 0.2,
            "volatility": 0.3,
            "rsi_slope": 0.1,
        }
    }
    securities = SecurityData(
        quote={},
        profile={},
        metrics=metrics,
        bars={},
        indicators={"AAPL": _indicator_records("AAPL", [100.0, 105.0, 110.0])},
    )
    return PortfolioData(
        summary={},
        holdings=holdings,
        metrics={"symbol": "PORTF", "name": "Portfolio", "rsi_slope": 0.0},
        indicators={"PORTF": _indicator_records("PORTF", [1.0, 1.05, 1.1])},
        correlation_matrix={"symbols": ["AAPL"], "entries": correlation_entries},
        securities=securities,
    )


def test_build_holdings_view_keeps_stock_and_option_rows():
    view = build_holdings_view(
        _mixed_portfolio([{"row": "AAPL", "col": "AAPL", "value": 1.0}]), ["AAPL"]
    )

    assert set(view.holdings_data.index) == {"AAPL", _OSI}
    # Both rows carry the underlying's analytics (joined via symbol, not index)
    assert view.holdings_data.loc[_OSI, "return1Y"] == pytest.approx(0.2)
    assert view.holdings_data.loc[_OSI, "sparkline"] is not None
    assert view.holdings_data.loc["AAPL", "sparkline"][-1] == pytest.approx(110.0)

    # Performance frame collapses to one row per symbol with weights rolled up
    assert list(view.performance_data.index) == ["AAPL"]
    assert view.performance_data.loc["AAPL", "weight"] == pytest.approx(0.9)

    # Transaction-form qty map holds equity rows only
    assert view.equity_qty == {"AAPL": 10}

    assert view.portfolio_metrics.index.tolist() == ["PORTF"]
    assert "signal" in view.portfolio_metrics.columns
    assert view.correlation_matrix.loc["AAPL", "AAPL"] == pytest.approx(1.0)


def test_build_holdings_view_missing_correlation_entries():
    view = build_holdings_view(_mixed_portfolio(None), ["AAPL"])
    assert view.correlation_matrix is None


def _two_account_portfolio() -> PortfolioData:
    """Total-portfolio shape: same symbol held in two accounts, keys namespaced."""

    def _holding(account: str, qty: int, weight: float, mv: float) -> dict:
        return {
            "symbol": "AAPL",
            "account": account,
            "name": "Apple",
            "exchange": "TEST",
            "close": 110.0,
            "currency": "CAD",
            "change_percent": 0.01,
            "timestamp": "2025-01-10T16:00:00",
            "open_qty": qty,
            "weight": weight,
            "market_value": mv,
            "holding_category": "Equity",
        }

    holdings = {
        "ACC-A|AAPL": _holding("ACC-A", 10, 0.5, 1100.0),
        "ACC-B|AAPL": _holding("ACC-B", 5, 0.25, 550.0),
    }
    metrics = {
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple",
            "return1Y": 0.2,
            "volatility": 0.3,
            "rsi_slope": 0.1,
        }
    }
    securities = SecurityData(
        quote={},
        profile={},
        metrics=metrics,
        bars={},
        indicators={"AAPL": _indicator_records("AAPL", [100.0, 105.0, 110.0])},
    )
    return PortfolioData(
        summary={},
        holdings=holdings,
        metrics={"symbol": "PORTF", "name": "Portfolio", "rsi_slope": 0.0},
        indicators={"PORTF": _indicator_records("PORTF", [1.0, 1.05, 1.1])},
        correlation_matrix={"symbols": ["AAPL"], "entries": None},
        securities=securities,
    )


def test_build_holdings_view_keeps_per_account_rows():
    view = build_holdings_view(_two_account_portfolio(), ["AAPL"])

    assert set(view.holdings_data.index) == {"ACC-A|AAPL", "ACC-B|AAPL"}
    assert set(view.holdings_data["account"]) == {"ACC-A", "ACC-B"}
    # Analytics join by symbol column, so every account row carries them
    assert view.holdings_data.loc["ACC-B|AAPL", "return1Y"] == pytest.approx(0.2)
    assert view.holdings_data.loc["ACC-A|AAPL", "sparkline"][-1] == pytest.approx(110.0)

    # Equity quantities sum across accounts
    assert view.equity_qty == {"AAPL": 15}

    # Performance frame collapses to one row per symbol with weights rolled up
    assert list(view.performance_data.index) == ["AAPL"]
    assert view.performance_data.loc["AAPL", "weight"] == pytest.approx(0.75)
