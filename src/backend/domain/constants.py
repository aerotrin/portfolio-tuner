"""
Global constants for *optimal-portfolio*.
"""

# ── Portfolio metrics ─────────────────────────────────────────────
RISK_FREE_RATE = 0.0300
TRADING_DAYS = 252
# Fewest daily returns a security needs before its volatility, risk share or
# correlations are reported
MIN_RETURN_OBS = 40
NEAR_HIGH_LOW_PCT = 0.025
SHORT_TERM_WINDOWS = {"5D": 5, "1M": 21, "3M": 63, "6M": 126}
RSI_WINDOW = 14
REL_VOLUME_WINDOW = 20
REL_VOLUME_MIN_OBS = 5
MERTON_CRA = 3
TREND_DAYS = 10
HYP_GROWTH_START = 10000

# ── Price chart ───────────────────────────────────────────────────
BOLLINGER_WINDOW = 20
BOLLINGER_STD = 2.0
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
PRICE_CHART_MA_PERIODS = (20, 50, 200)
PRICE_CHART_MA_MAX_COUNT = 5
PRICE_CHART_MA_MIN_PERIOD = 2
PRICE_CHART_MA_MAX_PERIOD = 250
# Visible sessions per range; YTD and MAX are derived from the data
PRICE_CHART_RANGE_SESSIONS = {**SHORT_TERM_WINDOWS, "1Y": TRADING_DAYS}
PRICE_CHART_RANGES = ("5D", "1M", "3M", "6M", "YTD", "1Y", "MAX")

# ── Visualizer and Optimizer ────────────────────────────────────
NUM_PORTFOLIOS = 5000
COR_PAIRS = 20
