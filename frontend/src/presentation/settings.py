# [Market] Number of securities to show in Market Movers section
MOVER_SHOW_COUNT = 36

# [Portfolio] Highlight limits for Take Profit and Loss in Positions Table
TAKE_PROFIT_LIMIT = 0.25  # positive value
LOSS_LIMIT = -0.10  # negative value

# [Portfolio] Default trading fees for new transactions
DEFAULT_TRADING_FEE = 6.95  # CAD per trade

# [Market/Portfolio] Range horizons mapping for Risk/Return Chart. Do not change!
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

TRADING_DAYS_PER_YEAR = 252

# [Market/Portfolio] Trade sizing guide for Transaction Form
TRADE_SIZING_GUIDE = {
    "1%": 0.01,
    "2%": 0.02,
    "5%": 0.05,
    "10%": 0.10,
}

# [Market/Portfolio] Treemap and Risk/Return Chart height defaults
HEIGHT_TREEMAP = 120
HEIGHT_RISK_RETURN_CHART = 450
HEIGHT_MARKET_SNAPSHOT = 150

# General color palette for styling tables and icons
GREEN = "#4CAF50"  # softer green for dark mode
RED = "#F44336"  # softer red for dark mode
GREEN_BG = "rgba(76,175,80,0.08)"
RED_BG = "rgba(244,67,54,0.08)"
NO_STYLE = ""  # fallback style
