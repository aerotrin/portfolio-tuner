from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from frontend.services.streamlit_data import PortfolioData, SecurityData
from frontend.shared.settings import TRADING_DAYS_PER_YEAR


def make_scalar_wide_df(data: dict[str, Any]) -> pd.DataFrame:
    if all(isinstance(v, dict) for v in data.values()):
        df = pd.DataFrame.from_dict(data, orient="index")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], errors="coerce", format="ISO8601"
            )
        return df

    # single record
    else:
        df = pd.DataFrame.from_records([data])
        if "symbol" not in df.columns:
            raise ValueError("Single-record dict must contain a 'symbol' key.")
        return df


def make_timeseries_wide_df(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    Make a wide dataframe from a dataframe of timeseries data for a given metric.
    The dataframe is pivoted on the date column, and the values are the timeseries data.
    """
    df = df.copy()
    df = df.pivot(index="date", columns="symbol", values=metric)
    df = df.sort_index().ffill()

    return df


def make_timeseries_long_df(data: dict[str, list]) -> pd.DataFrame:
    """
    Make a long dataframe from a dictionary of timeseries data.
    """
    records = []
    for _, values in data.items():
        for value in values:
            records.append(value)
    df = pd.DataFrame(records)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    else:
        raise ValueError("date column not found in data")
    return df


def add_sparkline(
    base_data: pd.DataFrame,
    close_eod: pd.DataFrame,
    add_intraday_close: bool = False,
    symbol_col: str | None = None,
) -> pd.DataFrame:
    """
    Fast sparkline generator with vectorized operations.

    Rows map to close_eod columns by index, or by `symbol_col` when the index
    is not the quote symbol (e.g. OSI-keyed option holdings).
    """
    base_data = base_data.copy()
    close_eod = close_eod.sort_index().ffill()

    # Pre-convert entire DataFrame → dict of {symbol: list_of_closes}
    series_dict = {symbol: col.dropna().tolist() for symbol, col in close_eod.items()}

    keys = base_data[symbol_col] if symbol_col else base_data.index
    base_data["sparkline"] = keys.map(series_dict.get)

    if add_intraday_close and "close" in base_data.columns:
        # Convert to lists with appended intraday close
        base_data["sparkline"] = [
            series + [close] if isinstance(series, list) else series
            for series, close in zip(base_data["sparkline"], base_data["close"])
        ]

    return base_data


def add_last_indicators(df: pd.DataFrame, indicators: pd.DataFrame) -> pd.DataFrame:
    """
    Add last calculated indicators to a dataframe.
    """
    df = df.copy()

    last_indicators = (
        indicators.sort_values("date").groupby("symbol", as_index=False).tail(1)
    ).copy()

    last_indicators = last_indicators.set_index("symbol", drop=True)

    df = df.merge(
        last_indicators.drop(columns=["date"]),
        left_index=True,
        right_index=True,
        how="left",
    )

    return df


def add_trade_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    macd_pos = df["macd_histogram"] > 0
    rsi_pos = df["rsi"] > 50
    rsi_up = df["rsi_slope"] > 0

    df["signal"] = np.select(
        [macd_pos & rsi_pos & rsi_up, macd_pos, rsi_pos & rsi_up],
        ["●●●", "●●○", "●○○"],
        default="",
    )

    df["signal"] += np.select(
        [df["rsi"] > 70, df["rsi"] < 30],
        ["⚠", "▽"],
        default="",
    )

    return df


def combine_header_data(
    header_symbols: list[str],
    securities: SecurityData,
) -> pd.DataFrame:
    """
    Make a header dataframe from the combined security data.
    """
    header = make_scalar_wide_df({s: securities.quote[s] for s in header_symbols})

    header_bars = make_timeseries_long_df(
        {s: securities.bars[s] for s in header_symbols}
    )
    header_closes = make_timeseries_wide_df(header_bars, "close")
    header = add_sparkline(header, header_closes, add_intraday_close=True)

    return header


@dataclass
class SecurityAnalytics:
    metrics: pd.DataFrame  # scalar wide: metrics + sparkline + last indicators
    indicators: pd.DataFrame  # long timeseries
    closes: pd.DataFrame  # wide timeseries "close"
    close_norm: pd.DataFrame  # wide timeseries "close_norm"


def build_security_analytics(
    symbols: list[str],
    securities: SecurityData,
) -> SecurityAnalytics:
    """Build enriched analytics DataFrames for a set of symbols from a SecurityData object."""
    metrics = make_scalar_wide_df({s: securities.metrics[s] for s in symbols})
    indicators = make_timeseries_long_df({s: securities.indicators[s] for s in symbols})
    closes = make_timeseries_wide_df(indicators, "close")
    close_norm = make_timeseries_wide_df(indicators, "close_norm")
    metrics = add_sparkline(metrics, closes)
    metrics = add_last_indicators(metrics, indicators)
    metrics = add_trade_signal(metrics)
    return SecurityAnalytics(
        metrics=metrics,
        indicators=indicators,
        closes=closes,
        close_norm=close_norm,
    )


@dataclass
class HoldingsView:
    holdings_data: pd.DataFrame  # positions + analytics metrics, index = holding key
    performance_data: pd.DataFrame  # one row per quote symbol, index = symbol
    close_norm: pd.DataFrame  # wide timeseries "close_norm" per symbol
    portfolio_metrics: pd.DataFrame  # single "PORTF" row with sparkline/indicators
    portfolio_close_norm: pd.DataFrame  # wide "PORTF" close_norm
    correlation_matrix: pd.DataFrame | None  # square symbol matrix
    equity_qty: dict[str, int]  # symbol -> open qty (equity rows only)


def build_holdings_view(portfolio: PortfolioData, symbols: list[str]) -> HoldingsView:
    """Build the holdings/portfolio DataFrames a portfolio page renders.

    Holdings are keyed by holding key (quote symbol, or OSI for options), so
    per-symbol analytics are joined via the 'symbol' column, not the index.
    """
    positions = make_scalar_wide_df(portfolio.holdings)

    analytics = build_security_analytics(symbols, portfolio.securities)
    positions = add_sparkline(
        positions, analytics.closes, add_intraday_close=True, symbol_col="symbol"
    )

    new_cols = analytics.metrics.columns.difference(positions.columns)
    holdings_data = positions.join(analytics.metrics[new_cols], on="symbol", how="left")

    equity = positions[positions["holding_category"] == "Equity"]
    # Group-sum: a symbol can appear once per account in the total view
    equity_qty = {
        str(s): int(q) for s, q in equity.groupby("symbol")["open_qty"].sum().items()
    }

    # Per-symbol view for the performance charts/table: quote and metric columns
    # are identical across a symbol's rows (they come from the underlying), so
    # collapse to one row per symbol with position weights rolled up.
    performance_data = holdings_data.copy()
    performance_data["weight"] = performance_data.groupby("symbol")["weight"].transform(
        "sum"
    )
    performance_data = performance_data[
        ~performance_data["symbol"].duplicated(keep="first")
    ].set_index("symbol", drop=False)

    portfolio_metrics = make_scalar_wide_df(portfolio.metrics)
    portfolio_metrics = portfolio_metrics.set_index("symbol", drop=False)

    portfolio_indicators = make_timeseries_long_df(portfolio.indicators)
    portfolio_closes = make_timeseries_wide_df(portfolio_indicators, "close")
    portfolio_close_norm = make_timeseries_wide_df(portfolio_indicators, "close_norm")

    correlation_matrix = None
    entries = (portfolio.correlation_matrix or {}).get("entries")
    if entries:
        correlation_matrix = pd.DataFrame(entries).pivot(
            index="row", columns="col", values="value"
        )

    portfolio_metrics = add_sparkline(portfolio_metrics, portfolio_closes)
    portfolio_metrics = add_last_indicators(portfolio_metrics, portfolio_indicators)
    portfolio_metrics = add_trade_signal(portfolio_metrics)

    return HoldingsView(
        holdings_data=holdings_data,
        performance_data=performance_data,
        close_norm=analytics.close_norm,
        portfolio_metrics=portfolio_metrics,
        portfolio_close_norm=portfolio_close_norm,
        correlation_matrix=correlation_matrix,
        equity_qty=equity_qty,
    )


def compute_correlation_matrix(
    closes: pd.DataFrame,
    symbols: list[str] | None = None,
) -> pd.DataFrame:
    """Correlation of daily returns over the trailing TRADING_DAYS_PER_YEAR window.

    Mirrors backend compute_correlation_matrix semantics (ffill, tail, pct_change, corr).
    """
    sub = closes.filter(items=symbols) if symbols is not None else closes
    C = sub.sort_index().ffill().tail(TRADING_DAYS_PER_YEAR)
    R = C.pct_change(fill_method=None).dropna(how="all")
    corr = R.corr()
    return corr.dropna(axis=0, how="all").dropna(axis=1, how="all")
