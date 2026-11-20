from datetime import datetime

import pytest

from src.backend.domain.aggregates.security import Security
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
