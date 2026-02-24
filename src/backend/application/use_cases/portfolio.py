import asyncio
from datetime import date
from typing import Any, List

from backend.application.use_cases.account import AccountManager
from backend.application.use_cases.market_data import MarketDataManager
from backend.domain.aggregates.portfolio import (
    Portfolio,
    PortfolioSnapshotDTO,
    PortfolioSummaryDTO,
)
from backend.domain.aggregates.portfolio_simulator import PortfolioSimulator
from backend.domain.entities.security import SecurityAnalyticsResponse


class PortfolioManager:
    """Use cases for managing portfolio data from market data and account data."""

    def __init__(
        self,
        market_man: MarketDataManager,
        account_man: AccountManager,
    ):
        self.market_man = market_man
        self.account_man = account_man

    async def build_portfolio_from_account(
        self,
        account_number: str,
        account_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Portfolio:
        account, rates = await asyncio.gather(
            asyncio.to_thread(
                self.account_man.build_account, account_number, account_name
            ),
            asyncio.to_thread(self.market_man.read_global_rates),
        )
        positions = account.open_positions
        symbols = [p.symbol for p in positions]
        securities = await self.market_man.build_securities_batch_async(
            symbols, start_date=start_date, end_date=end_date, rates=rates
        )
        return Portfolio(
            id=account_number,
            cash=account.cash_balance,
            external_cash_flows=account.external_cash_flows,
            positions=account.open_positions,
            securities=securities,
            rates=rates,
        )

    async def run_simulated_portfolio(
        self,
        symbols: List[str],
        n_p: int = 5000,
    ) -> dict[str, Any]:
        rates = await asyncio.to_thread(self.market_man.read_global_rates)
        securities_map = await self.market_man.build_securities_batch_async(
            symbols, rates=rates
        )
        securities = [securities_map[s] for s in symbols if s in securities_map]
        simulator = PortfolioSimulator(securities, rates, n_p)
        simulator.run_simulator()
        return simulator.find_optimal_portfolio()

    async def get_portfolio(
        self,
        account_number: str,
        account_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PortfolioSnapshotDTO:
        portfolio = await self.build_portfolio_from_account(
            account_number, account_name, start_date, end_date
        )
        per_sec = {
            symbol: SecurityAnalyticsResponse(
                quote=sec.quote,
                profile=sec.profile,
                bars=sec.bars,
                metrics=sec.metrics,
                indicators=sec.indicators,
            )
            for symbol, sec in portfolio.securities.items()
        }
        return PortfolioSnapshotDTO(
            summary=PortfolioSummaryDTO(
                id=portfolio.id,
                book_value=portfolio.book_value,
                market_value=portfolio.market_value,
                total_value=portfolio.total_value,
                cash_balance=portfolio.cash_balance,
                cash_pct=portfolio.cash_pct,
                unrealized_gain=portfolio.unrealized_gain,
                return_on_cost=portfolio.return_on_cost,
                return_on_value=portfolio.return_on_value,
                net_investment=portfolio.net_investment,
                mwrr=portfolio.mwrr,
                pnl_intraday=portfolio.pnl_intraday,
                open_positions=[h.symbol for h in portfolio.holdings.values()],
            ),
            holdings=portfolio.holdings,
            metrics=portfolio.metrics,
            indicators=portfolio.indicators,
            correlation_matrix=portfolio.correlation_matrix,
            securities=per_sec,
        )
