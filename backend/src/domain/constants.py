"""
Global constants for *optimal-portfolio*.
"""

# ── Portfolio metrics ─────────────────────────────────────────────
RISK_FREE_RATE = 0.0300
TRADING_DAYS = 252
NEAR_HIGH_LOW_PCT = 0.025
SHORT_TERM_WINDOWS = {"5D": 5, "1M": 21, "3M": 63, "6M": 126}
RSI_WINDOW = 14
MERTON_CRA = 3
TREND_DAYS = 10
HYP_GROWTH_START = 10000

# ── Visualizer and Optimizer ────────────────────────────────────
NUM_PORTFOLIOS = 5000
TAKE_PROFIT_LIMIT = 0.25
COR_PAIRS = 20
LOSS_LIMIT = -0.15
