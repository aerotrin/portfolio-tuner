from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.backend.domain.analytics.price_chart import (
    build_price_chart,
    compute_price_chart_indicators,
    compute_price_chart_ranges,
    merge_quote_bar,
    validate_ma_periods,
)
from src.backend.domain.analytics.security import (
    _calc_rsi,
    compute_timeseries_indicators,
)
from src.backend.domain.entities.security import Bar, Profile, Quote


def _frame(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1000.0}
    )


def _bars(closes: list[float], start: date = date(2024, 1, 1)) -> list[Bar]:
    return [
        Bar(
            symbol="AAA",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=100.0,
            date=start + timedelta(days=i),
        )
        for i, c in enumerate(closes)
    ]


def _quote(day: date, close: float = 50.0, **overrides) -> Quote:
    fields = dict(
        symbol="AAA",
        name="Triple A",
        exchange="NYSE",
        open=49.0,
        high=51.0,
        low=48.0,
        close=close,
        currency="USD",
        volume=500.0,
        change=1.5,
        change_percent=0.03,
        previousClose=48.5,
        timestamp=datetime(day.year, day.month, day.day, 15, 30),
    )
    fields.update(overrides)
    return Quote(**fields)


# ── Period validation ───────────────────────────────────────────────────────


def test_validate_ma_periods_dedupes_and_sorts() -> None:
    assert validate_ma_periods([50, 20, 50, 200]) == [20, 50, 200]
    assert validate_ma_periods([]) == []


@pytest.mark.parametrize("periods", [[1], [251], [2, 3, 4, 5, 6, 7], [True]])
def test_validate_ma_periods_rejects_out_of_bounds(periods) -> None:
    with pytest.raises(ValueError):
        validate_ma_periods(periods)


# ── Indicators ──────────────────────────────────────────────────────────────


def test_sma_has_null_warmup_and_hand_values() -> None:
    out = compute_price_chart_indicators(_frame([1, 2, 3, 4, 5]), ma_periods=[3])

    sma = out["ma_3"]
    assert sma.iloc[:2].isna().all()
    assert sma.iloc[2:].tolist() == [2.0, 3.0, 4.0]


def test_ema_masks_warmup_and_matches_unmasked_recursion() -> None:
    frame = _frame([float(v) for v in range(1, 31)])

    out = compute_price_chart_indicators(frame, ma_type="ema", ma_periods=[10])

    expected = frame["close"].ewm(span=10, adjust=False).mean()
    assert out["ma_10"].iloc[:9].isna().all()
    assert np.allclose(out["ma_10"].iloc[9:], expected.iloc[9:])


def test_bollinger_uses_population_std_around_sma20() -> None:
    closes = [float(v) for v in range(1, 26)]
    out = compute_price_chart_indicators(_frame(closes), ma_periods=[])

    window = np.array(closes[5:25])
    assert out["bb_middle"].iloc[:19].isna().all()
    assert out["bb_middle"].iloc[-1] == pytest.approx(window.mean())
    assert out["bb_upper"].iloc[-1] == pytest.approx(window.mean() + 2 * window.std())
    assert out["bb_lower"].iloc[-1] == pytest.approx(window.mean() - 2 * window.std())


def test_rsi_masks_warmup_and_matches_existing_calculation() -> None:
    rng = np.random.default_rng(7)
    frame = _frame((100 + rng.normal(0, 1, 60).cumsum()).tolist())

    out = compute_price_chart_indicators(frame, ma_periods=[])

    assert out["rsi"].iloc[:14].isna().all()
    assert np.allclose(out["rsi"].iloc[14:], _calc_rsi(frame["close"], 14).iloc[14:])


def test_rsi_is_100_when_there_are_no_losses() -> None:
    out = compute_price_chart_indicators(
        _frame([float(v) for v in range(1, 41)]), ma_periods=[]
    )

    assert (out["rsi"].iloc[14:] == 100.0).all()


def test_macd_matches_performance_indicators_after_warmup() -> None:
    rng = np.random.default_rng(11)
    frame = _frame((100 + rng.normal(0, 1, 80).cumsum()).tolist())

    out = compute_price_chart_indicators(frame, ma_periods=[])
    reference = compute_timeseries_indicators(frame.assign(symbol="AAA"))

    assert out["macd"].iloc[:25].isna().all()
    assert out["macd_signal"].iloc[:33].isna().all()
    assert out["macd_histogram"].iloc[:33].isna().all()
    assert np.allclose(out["macd"].iloc[25:], reference["macd_12_26"].iloc[25:])
    assert np.allclose(
        out["macd_signal"].iloc[33:], reference["macd_signal_9"].iloc[33:]
    )
    assert np.allclose(
        out["macd_histogram"].iloc[33:], reference["macd_histogram"].iloc[33:]
    )


# ── Today's bar ─────────────────────────────────────────────────────────────


def test_merge_quote_appends_a_new_last_bar() -> None:
    frame, used = merge_quote_bar(_bars([10, 11]), _quote(date(2024, 1, 3)))

    assert used
    assert len(frame) == 3
    assert frame.iloc[-1][["open", "high", "low", "close", "volume"]].tolist() == [
        49.0,
        51.0,
        48.0,
        50.0,
        500.0,
    ]


def test_merge_quote_premarket_zeros_become_a_flat_candle() -> None:
    quote = _quote(date(2024, 1, 3), open=0.0, high=0.0, low=0.0, volume=0.0)

    frame, used = merge_quote_bar(_bars([10, 11]), quote)

    last = frame.iloc[-1]
    assert used
    assert (last["open"], last["high"], last["low"], last["close"]) == (50, 50, 50, 50)
    assert last["volume"] == 0.0


def test_merge_quote_same_date_falls_back_to_stored_fields() -> None:
    quote = _quote(date(2024, 1, 2), close=11.5, open=0.0, high=0.0, low=0.0)

    frame, used = merge_quote_bar(_bars([10, 11]), quote)

    last = frame.iloc[-1]
    assert used and len(frame) == 2
    assert last["open"] == 11.0
    assert last["high"] == 12.0
    assert last["low"] == 10.0
    assert last["close"] == 11.5


def test_merge_quote_clamps_high_and_low_around_open_and_close() -> None:
    quote = _quote(date(2024, 1, 3), close=60.0, open=49.0, high=51.0, low=55.0)

    frame, _ = merge_quote_bar(_bars([10, 11]), quote)

    assert frame.iloc[-1]["high"] == 60.0
    assert frame.iloc[-1]["low"] == 49.0


def test_merge_quote_ignores_zero_close_and_stale_quotes() -> None:
    bars = _bars([10, 11])

    zero, zero_used = merge_quote_bar(bars, _quote(date(2024, 1, 3), close=0.0))
    stale, stale_used = merge_quote_bar(bars, _quote(date(2023, 12, 29)))

    assert not zero_used and len(zero) == 2
    assert not stale_used and len(stale) == 2


def test_merge_quote_sorts_and_dedupes_bars() -> None:
    bars = _bars([10, 11, 12])
    frame, _ = merge_quote_bar([bars[2], bars[0], bars[1], bars[1]], None)

    assert frame["close"].tolist() == [10.0, 11.0, 12.0]


# ── Ranges ──────────────────────────────────────────────────────────────────


def _ranges(close: pd.Series) -> dict:
    return {r.key: r for r in compute_price_chart_ranges(close)}


def test_ranges_measure_from_the_session_before_the_window() -> None:
    close = _frame([float(v) for v in range(100, 110)])["close"]

    ranges = _ranges(close)

    assert list(ranges) == ["5D", "1M", "3M", "6M", "YTD", "1Y", "MAX"]
    assert ranges["5D"].sessions == 5
    assert ranges["5D"].change == pytest.approx(109 - 104)
    assert ranges["5D"].change_percent == pytest.approx(5 / 104)


def test_ranges_short_history_has_no_change_but_shows_all_rows() -> None:
    ranges = _ranges(_frame([100.0, 101.0, 102.0])["close"])

    assert ranges["1M"].sessions == 3
    assert ranges["1M"].change is None
    assert ranges["MAX"].sessions == 3
    assert ranges["MAX"].change == pytest.approx(2.0)


def test_ranges_ytd_measures_from_last_close_of_prior_year() -> None:
    close = _frame([100.0, 110.0, 120.0, 130.0], start="2023-12-28")["close"]

    ytd = _ranges(close)["YTD"]

    # 2023-12-28, 2023-12-29, then 2024-01-01 and 2024-01-02
    assert ytd.sessions == 2
    assert ytd.change == pytest.approx(130.0 - 110.0)


def test_ranges_ytd_listed_this_year_measures_from_first_close() -> None:
    ytd = _ranges(_frame([100.0, 110.0, 120.0], start="2024-03-04")["close"])["YTD"]

    assert ytd.sessions == 3
    assert ytd.change == pytest.approx(20.0)


# ── Assembled chart ─────────────────────────────────────────────────────────


def test_build_price_chart_returns_none_without_data() -> None:
    assert build_price_chart("AAA", [], None, None) is None


def test_build_price_chart_from_quote_only() -> None:
    chart = build_price_chart("AAA", [], _quote(date(2024, 1, 3)), None)

    assert chart is not None
    assert chart.series.close == [50.0]
    assert chart.summary.change_1d == 1.5
    assert chart.summary.change_percent_1d == 0.03


def test_build_price_chart_summary_uses_quote_and_profile() -> None:
    quote = _quote(date(2024, 1, 3))
    profile = Profile(
        symbol="AAA",
        date=datetime(2024, 1, 1),
        marketCap=2.5e9,
        epsTrailing=2.5,
        epsForward=4.0,
        dividendRate=1.0,
        sharesOutstanding=1.0e8,
    )

    chart = build_price_chart("AAA", _bars([10, 11]), quote, profile)

    assert chart is not None
    summary = chart.summary
    assert summary.name == "Triple A"
    assert summary.currency == "USD"
    assert summary.last_price == 50.0
    assert summary.volume == 500.0
    # Derived from the quote price, not the stored market cap
    assert summary.market_cap == pytest.approx(5.0e9)
    assert summary.trailing_pe == pytest.approx(20.0)
    assert summary.forward_pe == pytest.approx(12.5)
    assert summary.eps == 2.5
    assert summary.dividend_yield == pytest.approx(0.02)
    assert summary.last_trade == quote.timestamp
    assert summary.day_high == 51.0
    assert summary.day_low == 48.0
    assert summary.high_52w == 51.0
    assert summary.low_52w == 9.0


def test_build_price_chart_without_quote_uses_last_two_closes() -> None:
    chart = build_price_chart("AAA", _bars([10, 11]), None, None)

    assert chart is not None
    assert chart.summary.change_1d == pytest.approx(1.0)
    assert chart.summary.change_percent_1d == pytest.approx(0.1)
    assert chart.summary.last_trade == datetime(2024, 1, 2)
    assert chart.summary.market_cap is None
    # Last stored session when no quote is merged
    assert chart.summary.day_high == 12.0
    assert chart.summary.day_low == 10.0


def test_build_price_chart_day_low_skips_a_zero_low() -> None:
    bars = _bars([10, 11])
    bars[-1] = bars[-1].model_copy(update={"low": 0.0})

    chart = build_price_chart("AAA", bars, None, None)

    assert chart is not None
    assert chart.summary.day_low is None
    assert chart.summary.day_high == 12.0


def test_build_price_chart_52_week_levels_use_last_252_sessions() -> None:
    closes = [500.0] + [100.0] * 260
    chart = build_price_chart("AAA", _bars(closes), None, None)

    assert chart is not None
    assert chart.summary.high_52w == 101.0
    assert chart.summary.low_52w == 99.0


def test_build_price_chart_series_has_nulls_not_nan() -> None:
    chart = build_price_chart(
        "AAA", _bars([float(v) for v in range(10, 50)]), None, None, ma_periods=[5, 200]
    )

    assert chart is not None
    series = chart.series
    assert [ma.period for ma in series.moving_averages] == [5, 200]
    assert series.moving_averages[0].values[:4] == [None] * 4
    assert all(v is None for v in series.moving_averages[1].values)
    assert series.rsi[0] is None and series.rsi[-1] is not None
    assert series.macd[0] is None
    payload = chart.model_dump_json()
    assert "NaN" not in payload


def test_build_price_chart_rejects_bad_periods() -> None:
    with pytest.raises(ValueError):
        build_price_chart("AAA", _bars([10, 11]), None, None, ma_periods=[1])
