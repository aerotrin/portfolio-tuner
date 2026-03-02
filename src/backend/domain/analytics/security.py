from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.domain.constants import (
    HYP_GROWTH_START,
    NEAR_HIGH_LOW_PCT,
    RISK_FREE_RATE,
    RSI_WINDOW,
    SHORT_TERM_WINDOWS,
    TRADING_DAYS,
)


def compute_portfolio_timeseries_indicators(
    securities: List["Security"],
    weights: np.ndarray,
) -> List[pd.DataFrame]:
    """
    Build a single weighted 'close' series across securities, then compute indicators
    on top of that (daily_return, ema12/26/100, rsi). Returns a DataFrame indexed by date.
    """
    if not securities:
        return [pd.DataFrame()]
    close_matrix = _calc_portfolio_weighted_close(securities, weights)

    daily = close_matrix.pct_change(fill_method=None)
    ema12 = close_matrix.ewm(span=12, adjust=False).mean()
    ema26 = close_matrix.ewm(span=26, adjust=False).mean()
    ema100 = close_matrix.ewm(span=100, adjust=False).mean()
    macd_12_26 = ema12 - ema26
    macd_signal_9 = macd_12_26.ewm(span=9, adjust=False).mean()
    macd_histogram = macd_12_26 - macd_signal_9
    rsi = _calc_rsi(close_matrix, RSI_WINDOW)
    rsi_signal_5 = rsi.rolling(window=5).mean()
    close_norm = close_matrix / close_matrix.iloc[0] * HYP_GROWTH_START

    out = []
    for portfolio in close_matrix.columns:
        close = close_matrix[portfolio]
        df = pd.DataFrame(index=close.index)
        df["symbol"] = portfolio
        df["close"] = close
        df["daily_return"] = daily[portfolio]
        df["ema12"] = ema12[portfolio]
        df["ema26"] = ema26[portfolio]
        df["ema100"] = ema100[portfolio]
        df["macd_12_26"] = macd_12_26[portfolio]
        df["macd_signal_9"] = macd_signal_9[portfolio]
        df["macd_histogram"] = macd_histogram[portfolio]
        df["rsi"] = rsi[portfolio]
        df["rsi_signal_5"] = rsi_signal_5[portfolio]
        df["close_norm"] = close_norm[portfolio]
        out.append(df)

    return out


def compute_timeseries_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute timeseries indicators from a dataframe of bars.
    Inherits the index from the dataframe as dates.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    close: pd.Series = df["close"].tail(TRADING_DAYS)

    daily_return = close.pct_change(fill_method=None)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    macd_12_26 = ema12 - ema26
    macd_signal_9 = macd_12_26.ewm(span=9, adjust=False).mean()
    macd_histogram = macd_12_26 - macd_signal_9
    rsi = _calc_rsi(close, RSI_WINDOW)
    rsi_signal_5 = rsi.rolling(window=5).mean()
    close_norm = close / close.iloc[0] * HYP_GROWTH_START

    out = pd.DataFrame(
        {
            "symbol": df["symbol"],
            "close": close,
            "daily_return": daily_return,
            "ema12": ema12,
            "ema26": ema26,
            "ema100": ema100,
            "macd_12_26": macd_12_26,
            "macd_signal_9": macd_signal_9,
            "macd_histogram": macd_histogram,
            "rsi": rsi,
            "rsi_signal_5": rsi_signal_5,
            "close_norm": close_norm,
        }
    )
    return out


def _calc_portfolio_weighted_close(
    securities: List["Security"],
    weights: np.ndarray,
) -> pd.DataFrame:
    """Return C: DataFrame (index=date, columns=symbols) with aligned close prices."""
    frames = []
    for sec in securities:
        s = sec.indicators_df["close"].copy()
        s.name = sec.quote.symbol
        frames.append(s)

    C = pd.concat(frames, axis=1, join="outer").sort_index().ffill()

    if len(C) > TRADING_DAYS:  # d
        C = C.iloc[-TRADING_DAYS:]

    W = np.asarray(weights, dtype=float)  # p × n matrix
    if W.ndim == 1:
        W = W.reshape(1, -1)  # ensure 2D array
    if W.shape[1] != len(C.columns):  # number of assets, n match number of weights
        raise ValueError("weights columns must equal number of assets")
    row_sums = W.sum(axis=1, keepdims=True)
    # Avoid divide-by-zero: use safe divisor then set zero-sum rows to equal weights
    safe_sums = np.where(row_sums > 0, row_sums, 1.0)
    W = W / safe_sums
    W = np.where(row_sums > 0, W, 1.0 / W.shape[1])
    M = (W @ C.T.values).T  # (p × n) @ (n × d) → (p × d); transpose back to (d × p)

    n_portfolios = W.shape[0]  # p
    if n_portfolios == 1:
        cols = ["PORTF"]
    else:
        cols = ["PORTF"] + [f"PORTF_{i}" for i in range(1, n_portfolios)]

    close = pd.DataFrame(M, index=C.index, columns=cols)
    return close


def _calc_asset_close_matrix(securities: List["Security"]) -> pd.DataFrame:
    frames = []
    for sec in securities:
        s = sec.indicators_df["close"].copy()
        s.name = sec.quote.symbol
        frames.append(s)
    C = pd.concat(frames, axis=1, join="outer").sort_index().ffill()
    if len(C) > TRADING_DAYS:
        C = C.iloc[-TRADING_DAYS:]
    return C


def compute_correlation_matrix(securities: List["Security"]) -> pd.DataFrame:
    C = _calc_asset_close_matrix(securities)
    R = C.pct_change(fill_method=None)
    R = R.dropna(how="all")
    return R.corr()


def compute_performance_metrics(
    df: pd.DataFrame, rf_rate: float = RISK_FREE_RATE
) -> pd.DataFrame:
    """
    Compute performance metrics from a dataframe of bars.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    daily: pd.Series = df["daily_return"]
    close: pd.Series = df["close"]
    rsi_signal_5: pd.Series = df["rsi_signal_5"]

    short_term_returns = _calc_short_term_returns(daily, SHORT_TERM_WINDOWS)
    annualized_return = _calc_annualized_return(daily, TRADING_DAYS)
    volatility = _calc_volatility(daily, TRADING_DAYS)
    sharpe = _calc_sharpe_daily(daily, rf_rate, TRADING_DAYS)
    sortino = _calc_sortino(daily, rf_rate, TRADING_DAYS)
    max_drawdown, max_drawdown_date = _calc_max_drawdown(daily)
    rsi_slope = _calc_rsi_slope(rsi_signal_5)
    flags = _calc_flags(close, NEAR_HIGH_LOW_PCT, TRADING_DAYS)
    symbol_val: Any = df["symbol"].iloc[0]
    out = {
        "symbol": symbol_val,
        **short_term_returns,
        "return1Y": annualized_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "max_drawdown_date": max_drawdown_date,
        "rsi_slope": rsi_slope,
        **flags,
        "last_calculated": datetime.now(),
    }
    return pd.DataFrame([out]).set_index("symbol")


def compute_performance_metrics_batch(
    timeseries: List[pd.DataFrame],
    rf_rate: float = RISK_FREE_RATE,
) -> pd.DataFrame:
    """
    Vectorized equivalent of [compute_performance_metrics(df, rf) for df in timeseries].

    Reconstructs wide (n_dates × n_p) matrices from the timeseries list, then computes
    every metric in a single pass of column-wise numpy/pandas operations.
    Returns a (n_p × metrics) DataFrame indexed by portfolio symbol — identical shape to
    pd.concat([compute_performance_metrics(df, rf) for df in timeseries]).

    Performance note: metric logic is intentionally inlined rather than delegated to the
    _calc_* helpers. Delegating via .apply() would restore SRP but reintroduce per-column
    Python loops, eliminating the vectorization speedup (20-100× for n_p=5000). Guards
    that live in the helpers (min_obs, sd==0, n>=days) are duplicated here deliberately
    and must be kept in sync if the helpers change.
    """
    if not timeseries:
        return pd.DataFrame()

    symbols: List[str] = [str(df["symbol"].iloc[0]) for df in timeseries]
    idx = pd.Index(symbols, name="symbol")

    daily = pd.concat(
        [df["daily_return"] for df in timeseries], axis=1, ignore_index=True
    )
    close = pd.concat([df["close"] for df in timeseries], axis=1, ignore_index=True)
    rsi5 = pd.concat(
        [df["rsi_signal_5"] for df in timeseries], axis=1, ignore_index=True
    )
    daily.columns = close.columns = rsi5.columns = idx

    r = daily.dropna(how="all")
    rf_daily = (1.0 + rf_rate) ** (1.0 / TRADING_DAYS) - 1.0
    excess = r - rf_daily

    n = len(r)

    short_returns: Dict[str, Any] = {}
    for label, days in SHORT_TERM_WINDOWS.items():
        vals = (1.0 + r.tail(days)).prod() - 1.0
        if n < days:
            vals[:] = np.nan
        short_returns[f"return{label}"] = vals

    if n == 0:
        ret1y = pd.Series(np.nan, index=idx)
    elif n >= TRADING_DAYS:
        ret1y = (1.0 + r.tail(TRADING_DAYS)).prod() - 1.0
    else:
        period_ret = (1.0 + r).prod() - 1.0
        ret1y = (1.0 + period_ret) ** (TRADING_DAYS / n) - 1.0
    vol = r.std() * np.sqrt(TRADING_DAYS)
    if n < 40:
        vol[:] = np.nan
    sharpe = (excess.mean() / excess.std().replace(0, np.nan)) * np.sqrt(TRADING_DAYS)

    downside = excess.clip(upper=0.0)
    dstd_ann = np.sqrt((downside**2).mean()) * np.sqrt(TRADING_DAYS)
    sortino = (excess.mean() * np.sqrt(TRADING_DAYS)) / dstd_ann.replace(0, np.nan)

    cum = (1.0 + r).cumprod()
    dd = cum / cum.cummax() - 1.0
    mdd = dd.min()
    mdd_dt = pd.to_datetime(dd.idxmin()).dt.date

    rsi_slope = (rsi5.iloc[-1] - rsi5.iloc[-2]) / 100.0

    closes_yr = close.tail(TRADING_DAYS)
    hi52 = closes_yr.max()
    lo52 = closes_yr.min()
    last = close.iloc[-1]
    near_hi = ((hi52 - last) / hi52.replace(0, np.nan)) <= NEAR_HIGH_LOW_PCT
    near_lo = ((last - lo52) / lo52.replace(0, np.nan)) <= NEAR_HIGH_LOW_PCT

    out = pd.DataFrame(short_returns, index=idx)
    out["return1Y"] = ret1y.values
    out["volatility"] = vol.values
    out["sharpe"] = sharpe.values
    out["sortino"] = sortino.values
    out["max_drawdown"] = mdd.values
    out["max_drawdown_date"] = mdd_dt.values
    out["rsi_slope"] = rsi_slope.values
    out["near_52wk_hi"] = near_hi.values
    out["near_52wk_lo"] = near_lo.values
    out["last_calculated"] = datetime.now()
    return out


def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate the Relative Strength Index (RSI) from a daily return series.
    """
    if close.empty:
        return pd.Series()
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs: pd.Series = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi: pd.Series = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.fillna(100.0)
    return rsi


def _calc_flags(
    close: pd.Series,
    near_hi_lo_pct: float,
    trading_days: int,
) -> dict[str, object]:
    """
    Add boolean flags to a 1-row dict:
      - near_52wk_hi / near_52wk_lo: within near_hi_lo_pct of 52-week high/low
    Uses the last trading_days as a "year".
    """
    out = {}
    if close.empty:
        return {
            "near_52wk_hi": pd.NA,
            "near_52wk_lo": pd.NA,
        }

    closes_year = close.tail(trading_days)
    hi52 = closes_year.max()
    lo52 = closes_year.min()
    thr = near_hi_lo_pct

    if pd.notna(hi52) and hi52 > 0 and pd.notna(close.iloc[-1]):
        near_hi = (hi52 - close.iloc[-1]) / hi52 <= thr
        out["near_52wk_hi"] = bool(near_hi)
    else:
        out["near_52wk_hi"] = pd.NA

    if pd.notna(lo52) and lo52 > 0 and pd.notna(close.iloc[-1]):
        near_lo = (close.iloc[-1] - lo52) / lo52 <= thr
        out["near_52wk_lo"] = bool(near_lo)
    else:
        out["near_52wk_lo"] = False

    return out


def _calc_annualized_return(ret: pd.Series, trading_days: int) -> float:
    """
    Scalar annualized return from a daily return series.
    """
    if ret.empty:
        return np.nan
    r = ret.dropna()
    n = len(r)
    if n == 0:
        return np.nan
    if n >= trading_days:
        return (1.0 + r.tail(trading_days)).prod() - 1.0
    period_ret = (1.0 + r).prod() - 1.0
    return (1.0 + period_ret) ** (trading_days / n) - 1.0


def _calc_short_term_returns(
    ret: pd.Series,
    windows: Dict[str, int],
) -> dict[str, float]:
    """
    Return a dictionary with '{label}_return' for each window size in days.
    """
    out: Dict[str, float] = {}
    if not windows:
        return out
    if ret.empty:
        return out
    r = ret.dropna()
    n = len(r)
    for label, days in windows.items():
        if n >= days:
            out[f"return{label}"] = (1.0 + r.tail(days)).prod() - 1.0
        else:
            out[f"return{label}"] = np.nan
    return out


def _calc_volatility(ret: pd.Series, trading_days: int, min_obs: int = 40) -> float:
    """
    Volatility from a daily return series.
    """
    if ret.empty:
        return np.nan
    r = ret.dropna()
    if len(r) < min_obs:
        return np.nan
    return r.std() * np.sqrt(trading_days)


def _calc_sharpe_daily(
    ret: pd.Series, rf_rate_annual: float, trading_days: int
) -> float:
    """
    Sharpe ratio from a daily return series.
    """
    if ret.empty:
        return np.nan
    r = ret.dropna()
    rf_daily = (1.0 + rf_rate_annual) ** (1.0 / trading_days) - 1.0
    excess = r - rf_daily
    sd = excess.std()
    if sd <= 0:
        return np.nan
    return (excess.mean() / sd) * np.sqrt(trading_days)


def _calc_sortino(ret: pd.Series, rf_rate_annual: float, trading_days: int) -> float:
    """
    Sortino ratio from a daily return series.
    """
    if ret.empty:
        return np.nan
    r = ret.dropna()
    if r.empty:
        return np.nan
    rf_daily = (1.0 + rf_rate_annual) ** (1.0 / trading_days) - 1.0
    downside = np.minimum(0.0, r - rf_daily)
    semi_var = np.mean(np.square(downside))
    dstd_ann = np.sqrt(semi_var) * np.sqrt(trading_days)
    if dstd_ann == 0:
        return np.nan
    ann_excess = (r - rf_daily).mean() * np.sqrt(trading_days)
    return ann_excess / dstd_ann


def _calc_max_drawdown(ret: pd.Series) -> Tuple[float, Optional[pd.Timestamp]]:
    """
    Return (max_drawdown, date_of_mdd) from a daily return series.
    """
    if ret.empty:
        return (np.nan, None)
    r = ret.dropna()
    if r.empty:
        return (np.nan, None)
    cum = (1.0 + r).cumprod()
    peak = cum.cummax()
    dd = (cum / peak) - 1.0  # ≤ 0
    mdd_date = dd.idxmin().date()  # FTRK-346
    mdd = float(dd.min())  # FTRK-337
    return (mdd, mdd_date)


def _calc_rsi_slope(rsi_signal_5: pd.Series) -> float:
    """1-bar RSI slope in normalized units [-1, 1]."""
    if len(rsi_signal_5) < 2:
        return np.nan
    return float((rsi_signal_5.iloc[-1] - rsi_signal_5.iloc[-2]) / 100.0)
