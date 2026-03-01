import asyncio
from typing import Any, List

from backend.application.use_cases.market_data import MarketDataManager
from backend.domain.aggregates.portfolio_simulator import SimPortfolios


class PortfolioSimulatorManager:
    """Use cases for simulating portfolio data."""

    def __init__(
        self,
        market_man: MarketDataManager,
    ):
        self.market_man = market_man

    async def _build_sim_portfolios(
        self,
        symbols: List[str],
        n_p: int = 5000,
    ) -> SimPortfolios:
        rates = await asyncio.to_thread(self.market_man.read_global_rates)
        securities_map = await self.market_man.build_securities_batch_async(
            symbols, rates=rates
        )
        securities = [securities_map[s] for s in symbols if s in securities_map]
        simulations = SimPortfolios(securities, rates, n_p)
        simulations.run()
        return simulations

    async def get_optimal_portfolio(
        self,
        symbols: List[str],
        n_p: int = 5000,
    ) -> dict[str, Any]:
        simulations = await self._build_sim_portfolios(symbols, n_p)
        return simulations.find_optimal_portfolio()
