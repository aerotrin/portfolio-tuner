"""The frontend's copies of backend values must equal their backend source.

`frontend/shared/constants.py` repeats some backend constants for labels and
input limits. This fails when one side is changed without the other.
"""

import pytest

from backend.application.use_cases.market_data import ANALYTICS_LOOKBACK_DAYS
from backend.domain import constants as backend
from frontend import settings
from frontend.shared import constants as frontend

MIRRORS = [
    ("TRADING_DAYS_PER_YEAR", "TRADING_DAYS"),
    ("MIN_RETURN_OBS", "MIN_RETURN_OBS"),
    ("PRICE_CHART_RANGES", "PRICE_CHART_RANGES"),
    ("PRICE_CHART_MA_MIN_PERIOD", "PRICE_CHART_MA_MIN_PERIOD"),
    ("PRICE_CHART_MA_MAX_PERIOD", "PRICE_CHART_MA_MAX_PERIOD"),
    ("PRICE_CHART_MA_MAX_COUNT", "PRICE_CHART_MA_MAX_COUNT"),
    ("RSI_WINDOW", "RSI_WINDOW"),
    ("MACD_FAST", "MACD_FAST"),
    ("MACD_SLOW", "MACD_SLOW"),
    ("MACD_SIGNAL", "MACD_SIGNAL"),
    ("BOLLINGER_WINDOW", "BOLLINGER_WINDOW"),
    ("BOLLINGER_STD", "BOLLINGER_STD"),
    ("REL_VOLUME_WINDOW", "REL_VOLUME_WINDOW"),
    ("HYP_GROWTH_START", "HYP_GROWTH_START"),
    ("OPTIMIZER_PORTFOLIOS_MAX", "NUM_PORTFOLIOS"),
]


@pytest.mark.parametrize(("frontend_name", "backend_name"), MIRRORS)
def test_frontend_copy_matches_backend(frontend_name, backend_name) -> None:
    assert getattr(frontend, frontend_name) == getattr(backend, backend_name)


def test_default_lookback_matches_the_analytics_window() -> None:
    assert frontend.DEFAULT_LOOKBACK_DAYS == ANALYTICS_LOOKBACK_DAYS


def test_return_horizons_follow_the_backend_windows() -> None:
    windows = {**backend.SHORT_TERM_WINDOWS, "1Y": backend.TRADING_DAYS}

    assert set(frontend.RETURN_HORIZONS) == set(windows)
    for label, horizon in frontend.RETURN_HORIZONS.items():
        assert horizon["trading_days"] == windows[label]
        assert horizon["metric"] == f"return{label}"


def test_period_sharpe_windows_follow_the_backend_windows() -> None:
    for label, days in frontend.PERIOD_SHARPE_WINDOWS.items():
        assert days == backend.SHORT_TERM_WINDOWS[label]


def test_price_chart_defaults_are_values_the_backend_accepts() -> None:
    defaults = settings.PRICE_CHART_DEFAULTS
    periods = [
        *defaults["ma_periods"],
        *settings.PRICE_CHART_MA_PERIOD_OPTIONS,
    ]

    assert defaults["range"] in backend.PRICE_CHART_RANGES
    assert len(defaults["ma_periods"]) <= backend.PRICE_CHART_MA_MAX_COUNT
    assert all(
        backend.PRICE_CHART_MA_MIN_PERIOD <= p <= backend.PRICE_CHART_MA_MAX_PERIOD
        for p in periods
    )


def test_optimizer_slider_stays_within_the_backend_limit() -> None:
    assert (
        settings.OPTIMIZER_PORTFOLIOS_MIN
        <= settings.OPTIMIZER_PORTFOLIOS_DEFAULT
        <= backend.NUM_PORTFOLIOS
    )


def test_series_palettes_cover_every_slot_the_charts_use() -> None:
    light, dark = settings.CHART_CATEGORICAL_LIGHT, settings.CHART_CATEGORICAL_DARK

    assert len(light) == len(dark)
    # The price chart draws its RSI line with slot 6
    assert len(light) >= 7
