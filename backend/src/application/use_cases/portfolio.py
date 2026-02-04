from typing import Any, List

from src.application.use_cases.account import AccountManager
from src.application.use_cases.market_data import MarketDataManager
from src.domain.aggregates.portfolio import (
    CorrelationMatrixDTO,
    Portfolio,
    PortfolioSummaryDTO,
)
from src.domain.aggregates.portfolio_simulator import PortfolioSimulator
from src.domain.entities.account import Holding
from src.domain.entities.security import PerformanceMetric, PortfolioIndicator


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
    def build_portfolio_from_account(
        self,
        account_number: str,
        account_name: str | None = None,
    ) -> Portfolio:
        account = self.account_man.build_account(account_number, account_name)
        positions = account.open_positions
        symbols = [p.symbol for p in positions]
        securities = {
            symbol: self.market_man.build_security(symbol) for symbol in symbols
        }
        portfolio = Portfolio(
            id=account_number,
            cash=account.cash_balance,
            positions=positions,
            securities=securities,
            rates=self.market_man.get_global_rates(),
        )
        return portfolio

    # --- Simulated portfolio use cases ---
    def run_simulated_portfolio(
        self,
        symbols: List[str],
        n_p: int = 5000,
    ) -> dict[str, Any]:
        rates = self.market_man.get_global_rates()
        securities = [self.market_man.build_security(symbol) for symbol in symbols]
        simulator = PortfolioSimulator(securities, rates, n_p)
        simulator.run_simulator()
        return simulator.find_optimal_portfolio()

    # --- Read / view-model use cases ---
    def get_portfolio_summary(
        self, account_number: str, account_name: str | None = None
    ) -> PortfolioSummaryDTO:
        portfolio = self.build_portfolio_from_account(account_number, account_name)
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

    def get_portfolio_holdings(
        self, account_number: str, account_name: str | None = None
    ) -> dict[str, Holding]:
        portfolio = self.build_portfolio_from_account(account_number, account_name)
        return portfolio.holdings

    def get_portfolio_indicators(
        self, account_number: str, account_name: str | None = None
    ) -> List[PortfolioIndicator]:
        portfolio = self.build_portfolio_from_account(account_number, account_name)
        return portfolio.indicators

    def get_portfolio_metrics(
        self, account_number: str, account_name: str | None = None
    ) -> PerformanceMetric:
        portfolio = self.build_portfolio_from_account(account_number, account_name)
        return portfolio.metrics

    def get_portfolio_correlation_matrix(
        self, account_number: str, account_name: str | None = None
    ) -> CorrelationMatrixDTO | None:
        portfolio = self.build_portfolio_from_account(account_number, account_name)
        return portfolio.correlation_matrix
