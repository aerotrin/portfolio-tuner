import asyncio
from datetime import datetime

import pytest

from src.backend.application.use_cases.simulator import PortfolioSimulatorManager
from src.backend.domain.entities.security import GlobalRates


class FakeMarketDataManager:
    def __init__(self):
        self.build_securities_batch_calls: list[dict] = []

    async def build_securities_batch_async(
        self, symbols, start_date=None, end_date=None, rates=None
    ):
        self.build_securities_batch_calls.append({"symbols": list(symbols)})
        return {s: object() for s in symbols}

    def read_global_rates(self):
        return GlobalRates(rf_rate=4.5, fx_rate=1.34)


def test_get_optimal_portfolio_delegates_to_sim_portfolios(monkeypatch):
    fake_market = FakeMarketDataManager()
    manager = PortfolioSimulatorManager(market_man=fake_market)

    captured = {}

    _run_at = datetime(2026, 3, 1, 12, 0, 0)

    class FakeSimPortfolios:
        def __init__(self, securities, rates, n_p, seed=None):
            captured["n_p"] = n_p
            captured["seed"] = seed
            self.ran = False
            self.run_at = _run_at

        def run(self):
            self.ran = True
            captured["ran"] = True

        def find_optimal_portfolio(self):
            assert self.ran is True
            return {"id": "PORTF_7", "sharpe": 2.1, "weights": {"AAPL": 0.7, "MSFT": 0.3}}

    monkeypatch.setattr(
        "src.backend.application.use_cases.simulator.SimPortfolios",
        FakeSimPortfolios,
    )

    portfolios, run_at = asyncio.run(
        manager.get_optimal_portfolio(symbols=["AAPL", "MSFT"], n_p=200, seed=99)
    )

    assert fake_market.build_securities_batch_calls == [{"symbols": ["AAPL", "MSFT"]}]
    assert captured["n_p"] == 200
    assert captured["seed"] == 99
    assert captured["ran"] is True
    assert portfolios == [{"id": "PORTF_7", "sharpe": 2.1, "weights": {"AAPL": 0.7, "MSFT": 0.3}}]
    assert run_at == _run_at


def test_get_optimal_portfolio_omits_seed_by_default(monkeypatch):
    """When seed is not passed it defaults to None (non-deterministic)."""
    fake_market = FakeMarketDataManager()
    manager = PortfolioSimulatorManager(market_man=fake_market)

    captured = {}

    class FakeSimPortfolios:
        def __init__(self, securities, rates, n_p, seed=None):
            captured["seed"] = seed
            self.run_at = datetime(2026, 3, 1)

        def run(self):
            pass

        def find_optimal_portfolio(self):
            return {"id": "PORTF_0", "weights": {}}

    monkeypatch.setattr(
        "src.backend.application.use_cases.simulator.SimPortfolios",
        FakeSimPortfolios,
    )

    asyncio.run(manager.get_optimal_portfolio(symbols=["AAPL"], n_p=10))

    assert captured["seed"] is None
