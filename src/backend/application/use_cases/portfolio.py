import asyncio
from datetime import date
from typing import Any

from backend.application.use_cases.account import AccountManager
from backend.application.use_cases.market_data import MarketDataManager
from backend.domain.aggregates.account import Account
from backend.domain.aggregates.portfolio import (
    AccountSliceDTO,
    Portfolio,
    PortfolioSnapshotDTO,
    PortfolioSummaryDTO,
    TotalPortfolioSnapshotDTO,
)
from backend.domain.entities.account import AccountEntity, CashFlow, OpenLot
from backend.domain.entities.security import GlobalRates, SecurityAnalyticsResponse

TOTAL_PORTFOLIO_ID = "TOTAL"


class PortfolioManager:
    """Use cases for managing portfolio data from market data and account data."""

    def __init__(
        self,
        market_man: MarketDataManager,
        account_man: AccountManager,
    ):
        self.market_man = market_man
        self.account_man = account_man

    async def _build_portfolio_from_account(
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

    @staticmethod
    def _to_snapshot_fields(portfolio: Portfolio) -> dict[str, Any]:
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
        return {
            "summary": PortfolioSummaryDTO(
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
                open_positions=sorted({h.symbol for h in portfolio.holdings.values()}),
            ),
            "holdings": portfolio.holdings,
            "metrics": portfolio.metrics,
            "indicators": portfolio.indicators,
            "correlation_matrix": portfolio.correlation_matrix,
            "securities": per_sec,
        }

    async def get_portfolio(
        self,
        account_number: str,
        account_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PortfolioSnapshotDTO:
        portfolio = await self._build_portfolio_from_account(
            account_number, account_name, start_date, end_date
        )
        return PortfolioSnapshotDTO(**self._to_snapshot_fields(portfolio))

    @staticmethod
    def _normalize_account_cash(
        entity: AccountEntity, account: Account, rates: GlobalRates
    ) -> tuple[float, list[CashFlow]]:
        """CAD-normalize an account's cash and external flows.

        Holdings are fx-converted per security inside Portfolio; account-level
        cash and flows are in the account's ledger currency, so USD accounts
        convert at the current fx rate (an approximation for historical flows).
        """
        fx = float(rates.fx_rate or 1.0) if entity.currency == "USD" else 1.0
        cash = account.cash_balance * fx
        flows = [
            cf if fx == 1.0 else cf.model_copy(update={"amount": cf.amount * fx})
            for cf in account.external_cash_flows
        ]
        return cash, flows

    async def get_total_portfolio(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TotalPortfolioSnapshotDTO:
        """Portfolio snapshot for all accounts combined.

        Pools cash, open lots (one per account and symbol/contract, each
        carrying its account number), and external cash flows into one
        pseudo-account, then runs the standard Portfolio pipeline — weights,
        MWRR, PORTF metrics, and correlation are computed over the combined
        holdings.
        """
        accounts = await asyncio.to_thread(self.account_man.list_accounts)

        def _build_all() -> list[Account]:
            return [self.account_man.build_account(a.number, a.name) for a in accounts]

        built, rates = await asyncio.gather(
            asyncio.to_thread(_build_all),
            asyncio.to_thread(self.market_man.read_global_rates),
        )

        total_cash = 0.0
        positions: list[OpenLot] = []
        all_flows: list[CashFlow] = []
        normalized: list[tuple[AccountEntity, Account, float, list[CashFlow]]] = []
        for entity, account in zip(accounts, built):
            cash, flows = self._normalize_account_cash(entity, account, rates)
            total_cash += cash
            positions.extend(account.open_positions)
            all_flows.extend(flows)
            normalized.append((entity, account, cash, flows))

        symbols = sorted({p.symbol for p in positions})
        securities = await self.market_man.build_securities_batch_async(
            symbols, start_date=start_date, end_date=end_date, rates=rates
        )

        total = Portfolio(
            id=TOTAL_PORTFOLIO_ID,
            cash=total_cash,
            external_cash_flows=all_flows,
            positions=positions,
            securities=securities,
            rates=rates,
        )

        # Per-account slices reuse the already-fetched securities (no extra I/O)
        slices = []
        for entity, account, cash, flows in normalized:
            acc_symbols = {p.symbol for p in account.open_positions}
            acc_portfolio = Portfolio(
                id=entity.number,
                cash=cash,
                external_cash_flows=flows,
                positions=account.open_positions,
                securities={s: securities[s] for s in acc_symbols if s in securities},
                rates=rates,
            )
            slices.append(
                AccountSliceDTO(
                    id=entity.id,
                    label=f"{entity.type} #{entity.number}",
                    name=entity.name,
                    total_value=acc_portfolio.total_value,
                    cash_balance=acc_portfolio.cash_balance,
                    unrealized_gain=acc_portfolio.unrealized_gain,
                    mwrr=acc_portfolio.mwrr,
                    weight=(
                        acc_portfolio.total_value / total.total_value
                        if total.total_value > 0
                        else 0.0
                    ),
                )
            )

        return TotalPortfolioSnapshotDTO(
            **self._to_snapshot_fields(total), accounts=slices
        )
