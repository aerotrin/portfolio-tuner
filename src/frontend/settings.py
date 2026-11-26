"""Everything you may want to tune about how the app looks and what it defaults to.

Change values here freely. Values that must agree with the backend, and other
internals, live in `frontend/shared/constants.py`; how numbers are computed is
set in `backend/domain/constants.py`; table columns are defined in
`frontend/shared/styles.py`.
"""

# ── Colours ─────────────────────────────────────────────────────────────────
# Gains / losses in tables; candles, volume and MACD bars on the price chart
GREEN = "#4CAF50"
RED = "#F44336"
# Row shading in tables (take-profit / stop-loss, near 52-week high / low)
GREEN_BG = "rgba(76,175,80,0.08)"
RED_BG = "rgba(244,67,54,0.08)"
# Clickable symbol cells; readable on light and dark
LINK_COLOR = "#3987e5"
# Benchmark line and marker on the growth, risk/return and frontier charts
BENCHMARK_COLOR = "magenta"

# Cash / securities donut in the account header
DONUT_SECURITIES_COLOR = "#4C8BF5"
DONUT_CASH_COLOR = "#9E9E9E"

# Series colours in fixed slot order (light / dark steps of the same hues) for
# the allocation charts and the price chart's lines. Keep both lists the same
# length, with at least 7 entries; extra allocation categories fold into "Other".
CHART_CATEGORICAL_LIGHT = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
]
CHART_CATEGORICAL_DARK = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#0ca30c",
    "#9085e9",
    "#e66767",
]
# "Other" slice, Bollinger lines, price chart panel labels
CHART_OTHER_COLOR = "#616161"

# Treemap change colours: down, flat, up. Red and green differ in lightness so
# they stay apart under red-green colour blindness.
CHANGE_COLOR_NEUTRAL = "#ECEFF1"
CHANGE_COLOR_SCALE = ["#D32F2F", CHANGE_COLOR_NEUTRAL, "#15803D"]
# Plotly colour scales: relative-volume treemap, correlation heatmap
REL_VOLUME_COLOR_SCALE = "Blues"
CORRELATION_COLOR_SCALE = "RdYlGn_r"

# "Last trade" badge in the page header
REFRESH_BADGE_FRESH_COLOR = "blue"
REFRESH_BADGE_STALE_COLOR = "yellow"

# ── Row highlighting and signals ────────────────────────────────────────────
# Holdings rows are shaded green at this total gain or more, red at this loss
TAKE_PROFIT_LIMIT = 0.25
LOSS_LIMIT = -0.10
# RSI levels: red / ⚠ above overbought, green / ▽ below oversold, and the
# "RSI in an up trend" level used by the Signal column. Also the shaded band
# on the price chart's RSI panel.
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_TREND = 50
# Minutes after which the "Last trade" badge turns stale
REFRESH_STALE_MINUTES = 60

# ── Treemaps ────────────────────────────────────────────────────────────────
# Tiles reach full colour at these moves, so one outlier cannot wash out the
# map and a shade means the same move every day.
CHANGE_COLOR_MAX = 0.04  # intraday change
TOTAL_RETURN_COLOR_MAX = 0.25  # total return on holdings
REL_VOLUME_COLOR_MAX = 3.0  # today's volume ÷ average
# Holding-age dots on Total Return tiles: one dot under the first value (days),
# one more at each threshold
AGE_DOT_BUCKETS = (30, 90, 180, 365)
TREEMAP_TILES_PER_ROW = 12
# px per row of tiles: market treemaps, then the larger holdings treemaps
HEIGHT_TREEMAP = 120
HEIGHT_POSITIONS_TREEMAP_ROW = 150
# Securities in each Market Movers treemap and table
MOVER_SHOW_COUNT = 36

# ── Chart and page sizes (px) ───────────────────────────────────────────────
PAGE_MAX_WIDTH = 1200
HEIGHT_RISK_RETURN_CHART = 450
HEIGHT_EFFICIENT_FRONTIER_CHART = 400
HEIGHT_MARKET_SNAPSHOT = 140
HEIGHT_ACCOUNT_DONUT = 72
HEIGHT_CASH_DONUT = 160
HEIGHT_ALLOCATION_CHART = 300
HEIGHT_ALLOCATION_BAR_ROW = 24  # per bar in Holdings by weight
HEIGHT_BREAKDOWN_DONUT = 240
SPARKLINE_WIDTH = 120  # "Price (1Y)" column

# ── Price chart ─────────────────────────────────────────────────────────────
# What the chart shows the first time it is opened in a session.
#   range:  5D, 1M, 3M, 6M, YTD, 1Y, MAX
# type: Candles, Line
#   show:   Moving averages, Bollinger bands, Volume, RSI, MACD, Price tags
#   ma_type: SMA, EMA
PRICE_CHART_DEFAULTS = {
    "range": "1Y",
    "type": "Candles",
    "show": ["Moving averages", "Volume", "RSI", "Price tags"],
    "ma_type": "SMA",
    "ma_periods": [20, 50, 200],
}
# Periods offered in the moving-average picker (others can be typed in)
PRICE_CHART_MA_PERIOD_OPTIONS = (10, 20, 50, 100, 200)
# px per panel, so the price panel keeps its size as panels are added
HEIGHT_PRICE_CHART_PANELS = {"price": 340, "volume": 90, "rsi": 110, "macd": 110}
HEIGHT_PRICE_CHART_GAP = 20

# ── Performance, allocation and optimizer ───────────────────────────────────
# Strongest / weakest pairs listed under the correlation matrix
CORRELATION_TOP_PAIRS = 3
# Holdings shown before the rest fold into "Other"
ALLOCATION_TOP_HOLDINGS = 15
# Random weights over many assets come out near-uniform, so the frontier loses
# meaning: warn above the first count, block above the second
WARN_OPTIMIZER_SYMBOLS = 25
MAX_OPTIMIZER_SYMBOLS = 50
# Simulated portfolios slider (its maximum is a backend limit)
OPTIMIZER_PORTFOLIOS_MIN = 1000
OPTIMIZER_PORTFOLIOS_STEP = 500
OPTIMIZER_PORTFOLIOS_DEFAULT = 2500

# ── Transactions ────────────────────────────────────────────────────────────
DEFAULT_TRADING_FEE = 6.95  # CAD per trade
# Position sizes listed in the trade sizing guide
TRADE_SIZING_GUIDE = {
    "1%": 0.01,
    "2%": 0.02,
    "5%": 0.05,
    "10%": 0.10,
    "15%": 0.15,
    "20%": 0.20,
}

# ── Refresh ─────────────────────────────────────────────────────────────────
# Seconds between progress updates while a background refresh runs
REFRESH_POLL_SEC = 1
# Seconds between checks for a due Auto refresh (the interval itself is
# AUTO_REFRESH_DATA_INTERVAL in .env)
AUTO_REFRESH_TICK_SEC = 10
# Failed symbols named in the warning before "and N more"
FAILED_SYMBOLS_SHOWN = 5

# ── Labels ──────────────────────────────────────────────────────────────────
# Short names on Market Snapshot cards; other symbols use the provider name
SNAPSHOT_DISPLAY_NAMES = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
    "^GSPTSE": "S&P/TSX",
    "^VIX": "VIX",
    "GC=F": "Gold",
    "SI=F": "Silver",
    "BZ=F": "Brent Crude",
    "GCUSD": "Gold",
    "SIUSD": "Silver",
    "BZUSD": "Brent Crude",
}
