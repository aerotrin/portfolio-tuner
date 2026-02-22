import asyncio
from typing import Any, List

from backend.application.use_cases.account import AccountManager
from backend.application.use_cases.market_data import MarketDataManager
from backend.domain.aggregates.portfolio import (
    CorrelationMatrixDTO,
    Portfolio,
    PortfolioSummaryDTO,
)
from backend.domain.aggregates.portfolio_simulator import PortfolioSimulator
from backend.domain.entities.account import Holding
from backend.domain.entities.security import PerformanceMetric, TimeseriesIndicator


class PortfolioManager:
    """Use cases for managing portfolio data from market data and account data."""

    def __init__(
        self,
        market_man: MarketDataManager,
        account_man: AccountManager,
    ):
        self.market_man = market_man
        self.account_man = account_man

    # --- Write / ETL use cases ---

    # --- Aggregate building helpers ---
    async def build_portfolio_from_account(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> Portfolio:
        account, rates = await asyncio.gather(
            asyncio.to_thread(self.account_man.build_account, account_number, account_name),
            asyncio.to_thread(self.market_man.get_global_rates),
        )
        positions = account.open_positions
        symbols = [p.symbol for p in positions]
        securities = await self.market_man.build_securities_batch_async(symbols, rates=rates)
        return Portfolio(
            id=account_number,
            cash=account.cash_balance,
            positions=positions,
            securities=securities,
            rates=rates,
        )

    # --- Simulated portfolio use cases ---
    async def run_simulated_portfolio(
        self,
        symbols: List[str],
        n_p: int = 5000,
    ) -> dict[str, Any]:
        rates = await asyncio.to_thread(self.market_man.get_global_rates)
        securities_map = await self.market_man.build_securities_batch_async(symbols, rates=rates)
        securities = [securities_map[s] for s in symbols if s in securities_map]
        simulator = PortfolioSimulator(securities, rates, n_p)
        simulator.run_simulator()
        return simulator.find_optimal_portfolio()

    # --- Read / view-model use cases ---
    async def get_portfolio_summary(
        self, account_number: str, account_name: str | None = None
    ) -> PortfolioSummaryDTO:
        portfolio = await self.build_portfolio_from_account(account_number, account_name)
        return PortfolioSummaryDTO(
            id=portfolio.id,
            book_value=portfolio.book_value,
            market_value=portfolio.market_value,
            total_value=portfolio.total_value,
            cash_balance=portfolio.cash_balance,
            cash_pct=portfolio.cash_pct,
            unrealized_gain=portfolio.unrealized_gain,
            return_on_cost=portfolio.return_on_cost,
            return_on_value=portfolio.return_on_value,
            pnl_intraday=portfolio.pnl_intraday,
            open_positions=[h.symbol for h in portfolio.holdings.values()],
        )

    async def get_portfolio_holdings(
        self, account_number: str, account_name: str | None = None
    ) -> dict[str, Holding]:
        portfolio = await self.build_portfolio_from_account(account_number, account_name)
        return portfolio.holdings

    async def get_portfolio_indicators(
        self, account_number: str, account_name: str | None = None
    ) -> List[TimeseriesIndicator]:
        portfolio = await self.build_portfolio_from_account(account_number, account_name)
        return portfolio.indicators

    async def get_portfolio_metrics(
        self, account_number: str, account_name: str | None = None
    ) -> PerformanceMetric:
        portfolio = await self.build_portfolio_from_account(account_number, account_name)
        return portfolio.metrics

    async def get_portfolio_correlation_matrix(
        self, account_number: str, account_name: str | None = None
    ) -> CorrelationMatrixDTO | None:
        portfolio = await self.build_portfolio_from_account(account_number, account_name)
        return portfolio.correlation_matrix
