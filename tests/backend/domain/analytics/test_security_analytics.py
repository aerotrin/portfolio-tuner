from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.backend.domain.analytics.security import (
    _calc_annualized_return,
    _calc_flags,
    _calc_max_drawdown,
    _calc_portfolio_weighted_close,
    _calc_rsi_slope,
    _calc_sharpe_daily,
    _calc_short_term_returns,
    _calc_sortino,
    _calc_volatility,
    compute_performance_metrics,
    compute_performance_metrics_batch,
    compute_portfolio_timeseries_indicators,
    compute_timeseries_indicators,
)
from src.backend.domain.constants import (
    RISK_FREE_RATE,
    SHORT_TERM_WINDOWS,
    TRADING_DAYS,
)


def _make_bars(symbol: str = "AAA", closes: list[float] | None = None) -> pd.DataFrame:
    closes = closes or [100.0, 101.0, 103.0, 102.0, 104.0, 105.0]
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"symbol": symbol, "close": closes}, index=idx)


def test_compute_timeseries_indicators_expected_columns_and_index() -> None:
    bars = _make_bars()

    out = compute_timeseries_indicators(bars)

    assert list(out.columns) == [
        "symbol",
        "close",
        "daily_return",
        "ema12",
        "ema26",
        "ema100",
        "macd_12_26",
        "macd_signal_9",
        "macd_histogram",
        "rsi",
        "rsi_signal_5",
        "close_norm",
    ]
    assert out.index.equals(bars.index)
    assert out["close"].iloc[0] == pytest.approx(bars["close"].iloc[0])


def test_compute_timeseries_indicators_empty_dataframe() -> None:
    assert compute_timeseries_indicators(pd.DataFrame()).empty


def test_compute_performance_metrics_schema_and_numeric_fields() -> None:
    bars = _make_bars(closes=[100, 101, 102, 101, 103, 105, 104, 106, 108, 110])
    indicators = compute_timeseries_indicators(bars)

    out = compute_performance_metrics(indicators, rf_rate=RISK_FREE_RATE)

    expected_columns = {
        *(f"return{label}" for label in SHORT_TERM_WINDOWS),
        "return1Y",
        "volatility",
        "sharpe",
        "sortino",
        "max_drawdown",
        "max_drawdown_date",
        "rsi_slope",
        "near_52wk_hi",
        "near_52wk_lo",
        "last_calculated",
    }
    assert set(out.columns) == expected_columns
    assert out.index.tolist() == ["AAA"]

    # core numeric fields should be finite with this non-degenerate dataset
    row = out.iloc[0]
    assert row["max_drawdown"] <= 0
    assert np.isfinite(row["rsi_slope"])


def test_compute_performance_metrics_all_nan_returns_stream() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    indicators = pd.DataFrame(
        {
            "symbol": ["AAA"] * 5,
            "close": [100, 100, 100, 100, 100],
            "daily_return": [np.nan] * 5,
            "rsi_signal_5": [np.nan] * 5,
        },
        index=idx,
    )

    out = compute_performance_metrics(indicators)
    row = out.iloc[0]

    assert np.isnan(row["return1Y"])
    assert np.isnan(row["volatility"])
    assert np.isnan(row["sharpe"])
    assert np.isnan(row["sortino"])
    assert np.isnan(row["max_drawdown"])
    assert row["max_drawdown_date"] is None


def test_calc_short_term_returns_short_history_and_empty() -> None:
    windows = {"2D": 2, "4D": 4}
    ret = pd.Series([0.01, -0.01, 0.02])

    out = _calc_short_term_returns(ret, windows)

    assert out["return2D"] == pytest.approx((1 - 0.01) * (1 + 0.02) - 1)
    assert np.isnan(out["return4D"])
    assert _calc_short_term_returns(pd.Series(dtype=float), windows) == {}


def test_calc_annualized_return_short_history_and_empty_and_all_nan() -> None:
    ret = pd.Series([0.01, 0.02, -0.01])
    period_ret = (1.01 * 1.02 * 0.99) - 1
    expected = (1 + period_ret) ** (TRADING_DAYS / 3) - 1

    assert _calc_annualized_return(ret, TRADING_DAYS) == pytest.approx(expected)
    assert np.isnan(_calc_annualized_return(pd.Series(dtype=float), TRADING_DAYS))
    assert np.isnan(_calc_annualized_return(pd.Series([np.nan, np.nan]), TRADING_DAYS))


def test_calc_volatility_min_obs_and_flat_returns() -> None:
    short = pd.Series([0.01] * 10)
    flat = pd.Series([0.0] * 45)

    assert np.isnan(_calc_volatility(short, TRADING_DAYS, min_obs=40))
    assert _calc_volatility(flat, TRADING_DAYS, min_obs=40) == pytest.approx(0.0)


def test_calc_sharpe_daily_flat_returns_zero_std() -> None:
    ret = pd.Series([0.0] * 50)

    sharpe = _calc_sharpe_daily(ret, rf_rate_annual=0.0, trading_days=TRADING_DAYS)

    assert np.isnan(sharpe)


def test_calc_sortino_downside_free_returns_and_empty() -> None:
    upside_only = pd.Series([0.01] * 30)

    assert np.isnan(
        _calc_sortino(upside_only, rf_rate_annual=0.0, trading_days=TRADING_DAYS)
    )
    assert np.isnan(_calc_sortino(pd.Series(dtype=float), 0.0, TRADING_DAYS))


def test_calc_max_drawdown_regular_and_empty_or_all_nan() -> None:
    ret = pd.Series(
        [0.1, -0.2, 0.05], index=pd.date_range("2024-01-01", periods=3, freq="D")
    )

    mdd, mdd_date = _calc_max_drawdown(ret)
    assert mdd == pytest.approx(-0.2)
    assert mdd_date == ret.index[1].date()

    empty_mdd, empty_date = _calc_max_drawdown(pd.Series(dtype=float))
    assert np.isnan(empty_mdd)
    assert empty_date is None

    nan_mdd, nan_date = _calc_max_drawdown(pd.Series([np.nan, np.nan]))
    assert np.isnan(nan_mdd)
    assert nan_date is None


def test_calc_flags_and_rsi_slope_edge_cases() -> None:
    empty_flags = _calc_flags(
        pd.Series(dtype=float), near_hi_lo_pct=0.025, trading_days=TRADING_DAYS
    )
    assert pd.isna(empty_flags["near_52wk_hi"])
    assert pd.isna(empty_flags["near_52wk_lo"])

    close = pd.Series([100.0, 102.0, 105.0, 103.0])
    flags = _calc_flags(close, near_hi_lo_pct=0.02, trading_days=TRADING_DAYS)
    assert flags["near_52wk_hi"] is True
    assert flags["near_52wk_lo"] is False

    assert np.isnan(_calc_rsi_slope(pd.Series([50.0])))
    assert _calc_rsi_slope(pd.Series([50.0, 55.0])) == pytest.approx(0.05)


def _sec(symbol: str, closes: list[float]) -> SimpleNamespace:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    indicators_df = pd.DataFrame({"close": closes}, index=idx)
    return SimpleNamespace(
        quote=SimpleNamespace(symbol=symbol), indicators_df=indicators_df
    )


def test_calc_portfolio_weighted_close_1d_and_2d_weights() -> None:
    securities = [
        _sec("AAA", [100, 110, 120]),
        _sec("BBB", [200, 220, 240]),
    ]

    out_1d = _calc_portfolio_weighted_close(securities, np.array([0.25, 0.75]))
    assert out_1d.columns.tolist() == ["PORTF"]
    assert out_1d.iloc[0, 0] == pytest.approx(175.0)

    out_2d = _calc_portfolio_weighted_close(
        securities,
        np.array(
            [
                [0.25, 0.75],
                [0.50, 0.50],
            ]
        ),
    )
    assert out_2d.columns.tolist() == ["PORTF", "PORTF_1"]
    assert out_2d.iloc[1, 0] == pytest.approx(192.5)
    assert out_2d.iloc[1, 1] == pytest.approx(165.0)


def test_calc_portfolio_weighted_close_zero_sum_row_fallback_and_shape_mismatch() -> (
    None
):
    securities = [
        _sec("AAA", [100, 100]),
        _sec("BBB", [200, 200]),
    ]

    out = _calc_portfolio_weighted_close(securities, np.array([[0.0, 0.0], [1.0, 3.0]]))
    # zero-sum row falls back to equal weights => mean(100, 200) = 150
    assert out.iloc[0, 0] == pytest.approx(150.0)
    # second row is normalized to 0.25/0.75 => 175
    assert out.iloc[0, 1] == pytest.approx(175.0)

    with pytest.raises(ValueError, match="weights columns must equal number of assets"):
        _calc_portfolio_weighted_close(securities, np.array([1.0, 2.0, 3.0]))


def test_compute_performance_metrics_batch_matches_loop_result() -> None:
    """Batch function output must match serial loop result for every numeric metric."""
    closes_a = [100 + i * 0.3 + (i % 4) * 0.1 for i in range(300)]
    closes_b = [80 + i * 0.2 + (i % 5) * 0.15 for i in range(300)]
    securities = [_sec("AAA", closes_a), _sec("BBB", closes_b)]

    weights = np.array([[0.6, 0.4], [0.3, 0.7], [0.5, 0.5]])
    timeseries = compute_portfolio_timeseries_indicators(securities, weights)

    loop_result = pd.concat(
        [compute_performance_metrics(df, RISK_FREE_RATE) for df in timeseries]
    )
    batch_result = compute_performance_metrics_batch(timeseries, RISK_FREE_RATE)

    assert set(loop_result.columns) == set(batch_result.columns)
    assert list(loop_result.index) == list(batch_result.index)

    for col in ["sharpe", "volatility", "sortino", "max_drawdown", "return1Y"]:
        pd.testing.assert_series_equal(
            loop_result[col],
            batch_result[col],
            check_names=False,
            atol=1e-10,
        )


def test_compute_performance_metrics_batch_empty_input() -> None:
    assert compute_performance_metrics_batch([]).empty
