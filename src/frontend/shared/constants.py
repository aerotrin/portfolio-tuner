"""Frontend values that are not free choices. Tunable settings are in `frontend/settings.py`.

The first block mirrors the backend: changing a value here alone makes the
frontend disagree with what the backend computes or accepts. Change the
backend constant named in the comment, then this copy;
`tests/test_settings_sync.py` fails while the two differ.
"""

# ── Must match the backend (backend/domain/constants.py unless noted) ───────
TRADING_DAYS_PER_YEAR = 252  # TRADING_DAYS
# Fewest daily returns before a security joins a correlation matrix
MIN_RETURN_OBS = 40  # MIN_RETURN_OBS
# Risk/Return chart horizons. `metric` is a backend field name and
# `trading_days` follows SHORT_TERM_WINDOWS / TRADING_DAYS.
RETURN_HORIZONS = {
    "1Y": {
        "metric": "return1Y",
        "days": 365,
        "trading_days": 252,
    },
    "6M": {
        "metric": "return6M",
        "days": 180,
        "trading_days": 126,
    },
    "3M": {
        "metric": "return3M",
        "days": 90,
        "trading_days": 63,
    },
    "1M": {
        "metric": "return1M",
        "days": 30,
        "trading_days": 21,
    },
    "5D": {
        "metric": "return5D",
        "days": 5,
        "trading_days": 5,
    },
}
# Trailing windows (trading days) for the optimizer's period Sharpe ratios
PERIOD_SHARPE_WINDOWS = {"1M": 21, "3M": 63}  # SHORT_TERM_WINDOWS

# Price chart: the backend returns a change figure per range and rejects
# moving-average periods outside these limits
PRICE_CHART_RANGES = ("5D", "1M", "3M", "6M", "YTD", "1Y", "MAX")  # PRICE_CHART_RANGES
PRICE_CHART_MA_MIN_PERIOD = 2  # PRICE_CHART_MA_MIN_PERIOD
PRICE_CHART_MA_MAX_PERIOD = 250  # PRICE_CHART_MA_MAX_PERIOD
PRICE_CHART_MA_MAX_COUNT = 5  # PRICE_CHART_MA_MAX_COUNT

# Indicator parameters, used here only to label what the backend computed
RSI_WINDOW = 14  # RSI_WINDOW
MACD_FAST = 12  # MACD_FAST
MACD_SLOW = 26  # MACD_SLOW
MACD_SIGNAL = 9  # MACD_SIGNAL
BOLLINGER_WINDOW = 20  # BOLLINGER_WINDOW
BOLLINGER_STD = 2  # BOLLINGER_STD
REL_VOLUME_WINDOW = 20  # REL_VOLUME_WINDOW
HYP_GROWTH_START = 10000  # HYP_GROWTH_START

# Most portfolios one optimizer run may simulate
OPTIMIZER_PORTFOLIOS_MAX = 5000  # NUM_PORTFOLIOS
# Days of history the analytics cover
# (backend/application/use_cases/market_data.py ANALYTICS_LOOKBACK_DAYS)
DEFAULT_LOOKBACK_DAYS = 365

# ── Labels built from the values above ──────────────────────────────────────
RSI_LABEL = f"RSI {RSI_WINDOW}"
MACD_LABEL = f"MACD ({MACD_FAST}, {MACD_SLOW}, {MACD_SIGNAL})"
BOLLINGER_LABEL = f"Bollinger ({BOLLINGER_WINDOW}, {BOLLINGER_STD})"
REL_VOLUME_HELP = f"Today's volume ÷ {REL_VOLUME_WINDOW}-day average volume"
GROWTH_LABEL = f"Growth of ${HYP_GROWTH_START:,}"
DAY_CHANGE_HELP = "Change since the previous close"
FUNDAMENTALS_HELP = (
    "P/E, yield and market cap use the last price with earnings, dividend and "
    "share figures refreshed weekly"
)

# ── Internals ───────────────────────────────────────────────────────────────
NO_STYLE = ""
# Shown in place of sensitive values when Hide Balances is on
MASKED_VALUE = "••••••••••••••••••••"
# Shown for a figure that is not available
MISSING_VALUE = "—"
