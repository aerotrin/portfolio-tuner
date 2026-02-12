from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.domain.aggregates.portfolio_simulator import PortfolioSimulator
from backend.domain.aggregates.security import Security
from backend.domain.entities.security import Bar, GlobalRates, Profile, Quote


def _build_security(symbol: str, prices: list[float], rates: GlobalRates) -> Security:
    now = datetime(2024, 1, 1)
    bars = [
        Bar(
            symbol=symbol,
            date=now + timedelta(days=i),
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=1_000_000 + i,
        )
        for i, price in enumerate(prices)
    ]

    quote = Quote(
        symbol=symbol,
        name=f"{symbol} Corp",
        exchange="NYSE",
        open=prices[-1],
        high=prices[-1] * 1.01,
        low=prices[-1] * 0.99,
        close=prices[-1],
        currency="USD",
        volume=1_000_000,
        change=0.0,
        change_percent=0.0,
        previousClose=prices[-1],
        timestamp=now,
    )
    profile = Profile(symbol=symbol, date=now)
    return Security(quote=quote, bars=bars, rates=rates, profile=profile)


def _build_securities() -> list[Security]:
    rates = GlobalRates(rf_rate=2.0, fx_rate=1.0)
    days = 140

    prices_a = [100 + i * 0.3 + (i % 4) * 0.1 for i in range(days)]
    prices_b = [80 + i * 0.2 + (i % 5) * 0.15 for i in range(days)]
    prices_c = [120 + i * 0.1 + (i % 3) * 0.2 for i in range(days)]

    return [
        _build_security("AAA", prices_a, rates),
        _build_security("BBB", prices_b, rates),
        _build_security("CCC", prices_c, rates),
    ]


def test_run_simulator_produces_expected_artifacts() -> None:
    securities = _build_securities()
    n_p = 4
    simulator = PortfolioSimulator(
        securities=securities,
        rates=GlobalRates(rf_rate=2.0, fx_rate=1.0),
        n_p=n_p,
    )

    np.random.seed(42)
    simulator.run_simulator()

    assert simulator.weight_matrix.shape == (n_p, len(securities))
    assert len(simulator.timeseries) == n_p
    assert not simulator.performance.empty
    assert list(simulator.performance.index) == ["PORTF", "PORTF_1", "PORTF_2", "PORTF_3"]


def test_find_optimal_portfolio_uses_max_sharpe_and_correct_weight_row() -> None:
    securities = _build_securities()
    simulator = PortfolioSimulator(
        securities=securities,
        rates=GlobalRates(rf_rate=2.0, fx_rate=1.0),
        n_p=3,
    )

    simulator.weight_matrix = np.array(
        [
            [0.7, 0.2, 0.1],
            [0.1, 0.6, 0.3],
            [0.25, 0.25, 0.5],
        ]
    )
    simulator.performance = pd.DataFrame(
        {"sharpe": [0.5, 1.6, 0.9], "volatility": [0.2, 0.15, 0.3]},
        index=["PORTF", "PORTF_1", "PORTF_2"],
    )

    result = simulator.find_optimal_portfolio()

    assert result["id"] == "PORTF_1"
    assert result["metrics"]["sharpe"] == pytest.approx(1.6)
    assert result["weights"] == {
        "AAA": pytest.approx(0.1),
        "BBB": pytest.approx(0.6),
        "CCC": pytest.approx(0.3),
    }


def test_find_optimal_portfolio_raises_before_run_simulator() -> None:
    simulator = PortfolioSimulator(
        securities=_build_securities(),
        rates=GlobalRates(rf_rate=2.0, fx_rate=1.0),
        n_p=2,
    )

    with pytest.raises(ValueError, match=r"Run run_simulator\(\) first"):
        simulator.find_optimal_portfolio()
