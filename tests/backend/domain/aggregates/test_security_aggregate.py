from datetime import datetime

import pytest

from src.backend.domain.aggregates.security import Security
from src.backend.domain.entities.security import Profile
from tests.backend.conftest import build_bars, build_global_rates, build_quote


def _security(n_bars: int, quote_volume: float) -> Security:
    closes = [100.0 + i for i in range(n_bars)]
    quote = build_quote(close=closes[-1], timestamp=datetime(2025, 6, 2, 16, 0, 0))
    return Security(
        quote=quote.model_copy(update={"volume": quote_volume}),
        bars=build_bars("AAPL", closes),
        rates=build_global_rates(),
    )


def test_metrics_carry_relative_volume_from_bars_and_quote():
    security = _security(n_bars=30, quote_volume=2_390_000.0)

    # Prior 20 sessions are bars 10..29: 1,100,000 .. 1,290,000
    assert security.metrics.avg_volume == pytest.approx(1_195_000.0)
    assert security.metrics.relative_volume == pytest.approx(2.0)


def test_relative_volume_is_none_with_short_history():
    security = _security(n_bars=3, quote_volume=2_000_000.0)

    assert security.metrics.relative_volume is None


def test_metrics_carry_dollar_volume_from_quote():
    security = _security(n_bars=30, quote_volume=2_000_000.0)

    assert security.metrics.dollar_volume == pytest.approx(2_000_000.0 * 129.0)


def _profiled_security(quote_close: float) -> Security:
    closes = [100.0 + i for i in range(30)]
    quote = build_quote(close=quote_close, timestamp=datetime(2025, 6, 2, 16, 0, 0))
    profile = Profile(
        symbol="AAPL",
        date=datetime(2025, 6, 1),
        epsTrailing=5.0,
        epsForward=8.0,
        dividendRate=2.0,
        sharesOutstanding=1.0e7,
    )
    return Security(
        quote=quote,
        bars=build_bars("AAPL", closes),
        rates=build_global_rates(),
        profile=profile,
    )


def test_metrics_carry_fundamentals_at_the_quote_price():
    metrics = _profiled_security(quote_close=200.0).metrics

    assert metrics.market_cap == pytest.approx(2.0e9)
    assert metrics.trailing_pe == pytest.approx(40.0)
    assert metrics.forward_pe == pytest.approx(25.0)
    assert metrics.eps == 5.0
    assert metrics.dividend_yield == pytest.approx(0.01)
    assert metrics.net_assets is None


def test_fundamentals_use_the_last_close_when_the_quote_has_no_price():
    metrics = _profiled_security(quote_close=0.0).metrics

    assert metrics.trailing_pe == pytest.approx(129.0 / 5.0)


def test_metrics_have_no_fundamentals_without_a_profile():
    metrics = _security(n_bars=30, quote_volume=2_000_000.0).metrics

    assert metrics.market_cap is None
    assert metrics.trailing_pe is None
    assert metrics.dividend_yield is None


def test_metrics_carry_the_52_week_range_from_bars_and_quote():
    metrics = _security(n_bars=30, quote_volume=2_000_000.0).metrics

    # The quote's high (129 + 1.5) tops the bars; the first bar's low is lowest
    assert metrics.high_52w == pytest.approx(130.5)
    assert metrics.low_52w == pytest.approx(98.0)


def test_52_week_range_ignores_an_unpriced_quote():
    closes = [100.0 + i for i in range(30)]
    quote = build_quote(close=0.0, timestamp=datetime(2025, 6, 2, 16, 0, 0))
    security = Security(
        quote=quote.model_copy(update={"high": 0.0, "low": 0.0}),
        bars=build_bars("AAPL", closes),
        rates=build_global_rates(),
    )

    assert security.metrics.high_52w == pytest.approx(130.0)
    assert security.metrics.low_52w == pytest.approx(98.0)
