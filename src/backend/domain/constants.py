"""How the numbers are computed: windows, periods and thresholds.

Changing a value here changes results. Values marked "mirrored" are repeated
in `frontend/shared/constants.py` for labels and input limits; change both
(`tests/test_settings_sync.py` fails while they differ).
"""

# ── Returns and risk ────────────────────────────────────────────────────────
# Fallback annual risk-free rate when a caller supplies none
RISK_FREE_RATE = 0.0300
# Sessions in a year: annualisation and the trailing window (mirrored)
TRADING_DAYS = 252
# Fewest daily returns a security needs before its volatility, risk share or
# correlations are reported (mirrored)
MIN_RETURN_OBS = 40
# Short-term return windows in sessions; the keys name the `return5D`…`return6M`
# metric fields (mirrored)
SHORT_TERM_WINDOWS = {"5D": 5, "1M": 21, "3M": 63, "6M": 126}
# Within this fraction of the 52-week high or low counts as "near"
NEAR_HIGH_LOW_PCT = 0.025
# Starting value of the normalised growth series (mirrored)
HYP_GROWTH_START = 10000

# ── Indicators ──────────────────────────────────────────────────────────────
RSI_WINDOW = 14  # mirrored
MACD_FAST = 12  # mirrored
MACD_SLOW = 26  # mirrored
MACD_SIGNAL = 9  # mirrored
# Long EMA and RSI smoothing of the performance indicator series. The API
# field names contain these numbers (`ema12`, `ema26`, `ema100`,
# `macd_signal_9`, `rsi_signal_5`), so changing a span means renaming a field.
EMA_LONG_SPAN = 100
RSI_SIGNAL_WINDOW = 5
BOLLINGER_WINDOW = 20  # mirrored
BOLLINGER_STD = 2.0  # mirrored
# Relative volume: sessions in the average, and the fewest it needs (mirrored)
REL_VOLUME_WINDOW = 20
REL_VOLUME_MIN_OBS = 5

# ── Price chart ─────────────────────────────────────────────────────────────
PRICE_CHART_MA_PERIODS = (20, 50, 200)
# Limits on user-chosen moving-average periods (mirrored)
PRICE_CHART_MA_MAX_COUNT = 5
PRICE_CHART_MA_MIN_PERIOD = 2
PRICE_CHART_MA_MAX_PERIOD = 250
# Visible sessions per range; YTD and MAX are derived from the data
PRICE_CHART_RANGE_SESSIONS = {**SHORT_TERM_WINDOWS, "1Y": TRADING_DAYS}
PRICE_CHART_RANGES = ("5D", "1M", "3M", "6M", "YTD", "1Y", "MAX")  # mirrored

# ── Optimizer ───────────────────────────────────────────────────────────────
# Default and maximum simulated portfolios per run (mirrored)
NUM_PORTFOLIOS = 5000
