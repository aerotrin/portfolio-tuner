from datetime import datetime, time
from typing import List, Literal, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from backend.domain.analytics.fundamentals import derive_fundamentals
from backend.domain.analytics.security import _calc_rsi
from backend.domain.constants import (
    BOLLINGER_STD,
    BOLLINGER_WINDOW,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    PRICE_CHART_MA_MAX_COUNT,
    PRICE_CHART_MA_MAX_PERIOD,
    PRICE_CHART_MA_MIN_PERIOD,
    PRICE_CHART_MA_PERIODS,
    PRICE_CHART_RANGE_SESSIONS,
    PRICE_CHART_RANGES,
    RSI_WINDOW,
    TRADING_DAYS,
)
from backend.domain.entities.security import (
    Bar,
    MovingAverageSeries,
    PriceChart,
    PriceChartRange,
    PriceChartSeries,
    PriceChartSummary,
    Profile,
    Quote,
)

MAType = Literal["sma", "ema"]
OHLCV = ["open", "high", "low", "close", "volume"]


def validate_ma_periods(periods: Sequence[int]) -> List[int]:
    """Deduplicated, sorted periods; raises ValueError when out of bounds."""
    unique = sorted(set(periods))
    if len(unique) > PRICE_CHART_MA_MAX_COUNT:
        raise ValueError(
            f"At most {PRICE_CHART_MA_MAX_COUNT} moving-average periods are allowed"
        )
    for period in unique:
        if isinstance(period, bool) or not isinstance(period, int):
            raise ValueError("Moving-average periods must be whole numbers")
        if not PRICE_CHART_MA_MIN_PERIOD <= period <= PRICE_CHART_MA_MAX_PERIOD:
            raise ValueError(
                "Moving-average periods must be between "
                f"{PRICE_CHART_MA_MIN_PERIOD} and {PRICE_CHART_MA_MAX_PERIOD}"
            )
    return unique


def merge_quote_bar(
    bars: Sequence[Bar], quote: Optional[Quote]
) -> Tuple[pd.DataFrame, bool]:
    """Date-indexed OHLCV frame with today's quote merged in as the last bar.

    Returns the frame and whether the quote supplied the last row. A quote
    whose open/high/low are not published yet (premarket) becomes a flat
    candle at the last price instead of a zero.
    """
    frame = pd.DataFrame([bar.model_dump() for bar in bars], columns=["date", *OHLCV])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = (
        frame.dropna(subset=["close"])
        .drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .set_index("date")
        .astype(float)
    )

    if quote is None or not quote.close > 0:
        return frame, False
    quote_date = pd.Timestamp(quote.timestamp.date())
    if not frame.empty and quote_date < frame.index[-1]:
        return frame, False

    stored = frame.loc[quote_date] if quote_date in frame.index else None
    close = float(quote.close)

    def pick(field: str) -> float:
        value = getattr(quote, field)
        if value > 0:
            return float(value)
        if stored is not None and stored[field] > 0:
            return float(stored[field])
        return 0.0 if field == "volume" else close

    open_ = pick("open")
    frame.loc[quote_date, OHLCV] = [
        open_,
        max(pick("high"), open_, close),
        min(pick("low"), open_, close),
        close,
        pick("volume"),
    ]
    return frame, True


def compute_price_chart_indicators(
    frame: pd.DataFrame,
    *,
    ma_type: MAType = "sma",
    ma_periods: Sequence[int] = PRICE_CHART_MA_PERIODS,
) -> pd.DataFrame:
    """Add indicator columns to an OHLCV frame. Warm-up rows are NaN."""
    out = frame.copy()
    close = out["close"]

    for period in ma_periods:
        if ma_type == "ema":
            out[f"ma_{period}"] = close.ewm(
                span=period, adjust=False, min_periods=period
            ).mean()
        else:
            out[f"ma_{period}"] = close.rolling(period, min_periods=period).mean()

    middle = close.rolling(BOLLINGER_WINDOW, min_periods=BOLLINGER_WINDOW).mean()
    band = BOLLINGER_STD * close.rolling(
        BOLLINGER_WINDOW, min_periods=BOLLINGER_WINDOW
    ).std(ddof=0)
    out["bb_middle"] = middle
    out["bb_upper"] = middle + band
    out["bb_lower"] = middle - band

    rsi = _calc_rsi(close, RSI_WINDOW).reindex(out.index)
    rsi.iloc[:RSI_WINDOW] = np.nan
    out["rsi"] = rsi

    # Same recursion as compute_timeseries_indicators; the warm-up is masked
    # by position because min_periods would reseed the signal line.
    macd = (
        close.ewm(span=MACD_FAST, adjust=False).mean()
        - close.ewm(span=MACD_SLOW, adjust=False).mean()
    )
    signal = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    histogram = macd - signal
    macd_warmup = MACD_SLOW - 1
    signal_warmup = macd_warmup + MACD_SIGNAL - 1
    out["macd"] = macd.mask(np.arange(len(out)) < macd_warmup)
    out["macd_signal"] = signal.mask(np.arange(len(out)) < signal_warmup)
    out["macd_histogram"] = histogram.mask(np.arange(len(out)) < signal_warmup)
    return out


def compute_price_chart_ranges(close: pd.Series) -> List[PriceChartRange]:
    """Visible sessions and price change for every range button.

    The change is measured from the close of the session before the first
    visible one, so fixed ranges match the performance table's returns.
    """
    n = len(close)
    last = float(close.iloc[-1]) if n else None

    def make(key: str, sessions: int, reference: Optional[float]) -> PriceChartRange:
        if last is None or reference is None or not reference > 0:
            return PriceChartRange(key=key, sessions=sessions)
        change = last - reference
        return PriceChartRange(
            key=key,
            sessions=sessions,
            change=change,
            change_percent=change / reference,
        )

    out = []
    for key in PRICE_CHART_RANGES:
        if key == "MAX":
            out.append(make(key, n, float(close.iloc[0]) if n else None))
        elif key == "YTD":
            sessions = int((close.index.year == close.index[-1].year).sum()) if n else 0
            # Listed this year: measure from its first close
            reference = float(close.iloc[max(n - sessions - 1, 0)]) if n else None
            out.append(make(key, sessions, reference))
        else:
            window = PRICE_CHART_RANGE_SESSIONS[key]
            reference = float(close.iloc[-(window + 1)]) if n > window else None
            out.append(make(key, min(window, n), reference))
    return out


def _nullable(series: pd.Series) -> List[Optional[float]]:
    values = series.to_numpy(dtype=float)
    return [float(v) if np.isfinite(v) else None for v in values]


def _finite(value: object) -> Optional[float]:
    if value is None:
        return None
    number = float(value)  # type: ignore[arg-type]
    return number if np.isfinite(number) else None


def _summarize(
    symbol: str,
    frame: pd.DataFrame,
    quote: Optional[Quote],
    profile: Optional[Profile],
    quote_used: bool,
) -> PriceChartSummary:
    close = frame["close"]
    last = float(close.iloc[-1])
    change = change_percent = None
    if quote_used and quote is not None and quote.previousClose > 0:
        # Same figures as the quote tables
        change, change_percent = float(quote.change), float(quote.change_percent)
    elif len(close) >= 2 and close.iloc[-2] > 0:
        change = last - float(close.iloc[-2])
        change_percent = change / float(close.iloc[-2])

    session = frame.iloc[-1]
    year = frame.tail(TRADING_DAYS)
    lows = year["low"][year["low"] > 0]
    if quote_used and quote is not None:
        last_trade = quote.timestamp
    else:
        last_trade = datetime.combine(frame.index[-1].date(), time.min)

    return PriceChartSummary(
        symbol=symbol,
        name=(quote.name if quote else None) or (profile.name if profile else None),
        exchange=(quote.exchange if quote else None)
        or (profile.exchange if profile else None),
        currency=(quote.currency if quote else None)
        or (profile.currency if profile else None),
        last_price=last,
        change_1d=change,
        change_percent_1d=change_percent,
        day_high=_finite(session["high"]) if session["high"] > 0 else None,
        day_low=_finite(session["low"]) if session["low"] > 0 else None,
        high_52w=_finite(year["high"].max()),
        low_52w=_finite(lows.min()) if not lows.empty else None,
        volume=_finite(session["volume"]),
        **derive_fundamentals(profile, last).model_dump(),
        last_trade=last_trade,
    )


def build_price_chart(
    symbol: str,
    bars: Sequence[Bar],
    quote: Optional[Quote],
    profile: Optional[Profile],
    *,
    ma_type: MAType = "sma",
    ma_periods: Sequence[int] = PRICE_CHART_MA_PERIODS,
) -> Optional[PriceChart]:
    """Daily OHLCV series with indicators, range changes and header figures.

    Returns None when there is neither a stored bar nor a usable quote.
    """
    periods = validate_ma_periods(ma_periods)
    frame, quote_used = merge_quote_bar(bars, quote)
    if frame.empty:
        return None
    data = compute_price_chart_indicators(frame, ma_type=ma_type, ma_periods=periods)

    series = PriceChartSeries(
        dates=[ts.date() for ts in data.index],
        moving_averages=[
            MovingAverageSeries(
                kind=ma_type, period=period, values=_nullable(data[f"ma_{period}"])
            )
            for period in periods
        ],
        **{
            column: _nullable(data[column])
            for column in [
                *OHLCV,
                "bb_middle",
                "bb_upper",
                "bb_lower",
                "rsi",
                "macd",
                "macd_signal",
                "macd_histogram",
            ]
        },
    )
    return PriceChart(
        summary=_summarize(symbol, frame, quote, profile, quote_used),
        ranges=compute_price_chart_ranges(frame["close"]),
        series=series,
    )
