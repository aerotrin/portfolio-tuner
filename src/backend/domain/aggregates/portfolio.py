from datetime import date, datetime
from functools import partial
import logging
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd
from pydantic import BaseModel

from backend.domain.aggregates.security import Security
from backend.domain.analytics.fixed_income import (
    accrual_index,
    accrued_interest,
    days_to_maturity,
    instrument_label,
    instrument_status,
    maturity_value,
)
from backend.domain.analytics.security import (
    SteadyAsset,
    compute_performance_metrics,
    compute_portfolio_timeseries_indicators,
    compute_return_statistics,
)
from backend.domain.analytics.summary_export import SummaryRow
from backend.domain.constants import MIN_RETURN_OBS
from backend.domain.entities.account import Category, CashFlow, Holding, OpenLot
from backend.domain.entities.security import (
    GlobalRates,
    PerformanceMetric,
    SecurityAnalyticsResponse,
    SecurityType,
    TimeseriesIndicator,
)

logger = logging.getLogger(__name__)

MULTIPLIER = 100


def _flat_growth(dates: Sequence[date]) -> np.ndarray:
    """Growth path of a holding with unknown terms: it stays at book value."""
    return np.ones(len(dates))


class CorrelationEntry(BaseModel):
    row: str
    col: str
    value: float


class CorrelationMatrixDTO(BaseModel):
    symbols: Optional[list[str]] = None
    entries: Optional[list[CorrelationEntry]] = None
    excluded: Optional[list[str]] = None
    as_of: Optional[datetime] = None


class PortfolioSummaryDTO(BaseModel):
    id: str
    book_value: float
    market_value: float
    total_value: float
    cash_balance: float
    cash_pct: float
    unrealized_gain: float
    return_on_cost: float
    return_on_value: float
    net_investment: float
    mwrr: float
    pnl_intraday: float
    open_positions: List[str]


class AccountSliceDTO(BaseModel):
    """Per-account summary line inside a portfolio snapshot.

    `cash_balance` is CAD-normalized; `cash_balance_native` is in the
    account's ledger `currency`.
    """

    id: str
    label: str
    name: str
    currency: str
    total_value: float
    cash_balance: float
    cash_balance_native: float
    unrealized_gain: float
    mwrr: float
    weight: float


class AllocationSliceDTO(BaseModel):
    label: str
    market_value: float
    weight: float


class SymbolWeightDTO(BaseModel):
    symbol: str
    name: str
    market_value: float
    weight: float
    shares_value: float
    options_value: float
    fixed_income_value: float = 0.0


class ConcentrationDTO(BaseModel):
    holdings: int = 0
    top1: float = 0.0
    top5: float = 0.0
    top10: float = 0.0
    hhi: float = 0.0
    effective_n: float = 0.0


class RiskContributionDTO(BaseModel):
    symbol: str
    weight: float
    risk_share: Optional[float] = None


class AccountMixSliceDTO(BaseModel):
    account: str
    label: str
    market_value: float
    weight: float


class AllocationDTO(BaseModel):
    """Allocation analytics over holdings plus positive cash, in CAD.

    `breakdowns` is keyed by dimension (asset_type, instrument, sector,
    country, currency, account); `account` labels are account numbers.
    `margin` is the negative cash left out of the breakdowns.
    """

    by_symbol: List[SymbolWeightDTO] = []
    breakdowns: dict[str, List[AllocationSliceDTO]] = {}
    concentration: ConcentrationDTO = ConcentrationDTO()
    risk_contribution: List[RiskContributionDTO] = []
    account_mix: List[AccountMixSliceDTO] = []
    margin: float = 0.0


class PortfolioSnapshotDTO(BaseModel):
    summary: PortfolioSummaryDTO
    holdings: dict[str, Holding]
    metrics: PerformanceMetric
    indicators: List[TimeseriesIndicator]
    correlation_matrix: Optional[CorrelationMatrixDTO]
    securities: dict[str, SecurityAnalyticsResponse] = {}
    accounts: List[AccountSliceDTO] = []
    allocation: AllocationDTO = AllocationDTO()
    summary_rows: List[SummaryRow] = []


class TotalPortfolioSnapshotDTO(PortfolioSnapshotDTO):
    pass


class Portfolio:
    """A portfolio is composed of securities for a given set of open positions."""

    def __init__(
        self,
        id: str,
        cash: float,
        positions: List[OpenLot],
        external_cash_flows: list[CashFlow],
        securities: dict[str, Security],
        rates: GlobalRates,
    ):
        self.id = id
        self.cash_balance = cash
        self.positions = positions
        self.external_cash_flows = external_cash_flows
        self.securities = securities
        self.rf_rate = float(rates.rf_rate or 0.0)
        self.fx_rate = float(rates.fx_rate or 1.0)

        self.indicators_df: pd.DataFrame = pd.DataFrame()
        self.indicators: List[TimeseriesIndicator] = []

        self.correlation_matrix_df: pd.DataFrame = pd.DataFrame()
        self.correlation_matrix: CorrelationMatrixDTO = CorrelationMatrixDTO()
        self.covariance_matrix_df: pd.DataFrame = pd.DataFrame()
        self.return_observations: pd.Series = pd.Series(dtype=float)

        self.holdings: dict[str, Holding] = {}
        # Fixed-income holding key -> the lot it was built from
        self._fixed_income_lots: dict[str, OpenLot] = {}

        self.book_value: float = 0.0
        self.market_value: float = 0.0
        self.total_value: float = cash
        self.cash_pct: float = 1.0

        self.unrealized_gain: float = 0.0
        self.return_on_cost: float = 0.0
        self.return_on_value: float = 0.0
        self.pnl_intraday: float = 0.0

        self.net_investment: float = 0.0
        self.mwrr: float = 0.0

        self.metrics = PerformanceMetric(
            symbol="PORTF",
            name="Portfolio",
            exchange="N/A",
            currency="CAD",
        )

        self.build()

    def _fixed_income_holding(self, position: OpenLot) -> Holding:
        """Value a fixed-income lot from its terms; it has no market quote.

        Without terms (a ledger row that couldn't be parsed) it stays at book.
        """
        today = date.today()
        terms = position.terms
        currency = str(position.currency or "CAD")
        fx_rate = self.fx_rate if currency == "USD" else 1.0

        fi_fields: dict = {}
        if terms is not None:
            principal = (
                position.principal
                if position.principal is not None
                else position.book_value
            )
            accrued = accrued_interest(
                principal, terms, today, position.interest_received
            )
            native_value = principal + accrued
            market_value = native_value * fx_rate
            name = instrument_label(terms)
            fi_fields = dict(
                fi_type=terms.type,
                fi_rate=terms.annual_rate,
                fi_issue_date=terms.issue_date,
                fi_maturity_date=terms.maturity_date,
                fi_days_to_maturity=days_to_maturity(terms, today),
                fi_status=instrument_status(terms, today),
                fi_payment_frequency=str(terms.payment_frequency),
                fi_principal=principal,
                fi_accrued_interest=accrued,
                fi_interest_received=position.interest_received,
                fi_maturity_value=maturity_value(principal, terms),
            )
        else:
            native_value = market_value = position.book_value
            name = "Fixed income (terms unknown)"

        unit_value = native_value / position.open_qty if position.open_qty else 0.0
        return Holding(
            symbol=position.symbol,
            account=position.account,
            name=name,
            open=unit_value,
            high=unit_value,
            low=unit_value,
            close=unit_value,
            currency=currency,
            volume=0.0,
            change=0.0,
            change_percent=0.0,
            previous_close=unit_value,
            holding_category=position.category,
            security_type=SecurityType.GIC,
            fx_rate=fx_rate,
            open_date=position.open_date,
            open_qty=position.open_qty,
            breakeven_price=0.0,
            book_value=position.book_value,
            market_value=market_value,
            gain=market_value - position.book_value,
            gain_pct=(
                (market_value - position.book_value) / position.book_value
                if position.book_value != 0.0
                else 0.0
            ),
            weight=0.0,
            intraday_change=0.0,
            intraday_change_pct=0.0,
            distance_to_breakeven=0.0,
            fx_exposure=(
                market_value - (market_value / fx_rate) if fx_rate != 1.0 else 0.0
            ),
            pnl_contribution=0.0,
            intraday_contribution=0.0,
            days_held=(today - position.open_date).days,
            **fi_fields,
        )

    def _build_holdings(self) -> None:
        try:
            # Keys stay plain (symbol/OSI) for a single account; only a
            # multi-account portfolio namespaces them so same-symbol positions
            # from different accounts don't collide.
            multi_account = len({p.account for p in self.positions}) > 1
            for position in self.positions:
                if position.category == Category.FIXED_INCOME:
                    key = position.symbol
                    if multi_account:
                        key = f"{position.account}|{key}"
                    self.holdings[key] = self._fixed_income_holding(position)
                    self._fixed_income_lots[key] = position
                    continue
                security = self.securities[position.symbol]
                if security:
                    close = security.quote.close
                    change = security.quote.change
                    change_percent = security.quote.change_percent

                    option_value = None
                    option_change = None
                    option_change_pct = None

                    currency = security.quote.currency
                    fx_rate = self.fx_rate if currency == "USD" else 1.0

                    days_held = (date.today() - position.open_date).days
                    option_dte = None
                    option_expired = None

                    # value calculations
                    intraday_change = 0.0
                    intraday_change_pct = 0.0
                    market_value = 0.0
                    breakeven_price = 0.0
                    distance_to_breakeven = 0.0
                    if position.category == Category.EQUITY:
                        market_value = close * position.open_qty * fx_rate
                        breakeven_price = (
                            position.acb_per_sh / fx_rate if fx_rate > 0.0 else 0.0
                        )
                        distance_to_breakeven = (
                            (close - breakeven_price) / breakeven_price
                            if breakeven_price != 0.0
                            else 0.0
                        )
                        intraday_change = change * position.open_qty * fx_rate
                        intraday_change_pct = change_percent
                    elif position.category == Category.CALL_OPTION:
                        option_dte = (
                            (position.option_expiry - date.today()).days
                            if position.option_expiry
                            else None
                        )
                        if option_dte and option_dte < 0:
                            option_expired = True
                            option_value = 0.0
                            option_change = 0.0
                            option_change_pct = 0.0
                        else:
                            option_expired = False
                            option_value = max(
                                float(close) - float(position.option_strike or 0.0), 0.0
                            )  # TODO: change to option_price when available
                            option_change = (
                                0.0  # TODO: change to option_change when available
                            )
                            option_change_pct = (
                                0.0  # TODO: change to option_change_pct when available
                            )

                            market_value = (
                                option_value * position.open_qty * MULTIPLIER * fx_rate
                            )
                            breakeven_price = (
                                position.acb_per_sh / (fx_rate * MULTIPLIER)
                                if fx_rate > 0.0
                                else 0.0
                            )
                            distance_to_breakeven = (
                                (option_value - breakeven_price) / breakeven_price
                                if breakeven_price != 0.0
                                else 0.0
                            )
                            intraday_change = (
                                option_change * position.open_qty * MULTIPLIER * fx_rate
                            )
                            intraday_change_pct = option_change_pct
                    elif position.category == Category.PUT_OPTION:
                        option_dte = (
                            (position.option_expiry - date.today()).days
                            if position.option_expiry
                            else None
                        )
                        if option_dte and option_dte < 0:
                            option_expired = True
                            option_value = 0.0
                            option_change = 0.0
                            option_change_pct = 0.0
                        else:
                            option_expired = False
                            option_value = max(
                                float(position.option_strike or 0.0) - float(close), 0.0
                            )  # TODO: change to option_price when available
                            option_change = (
                                0.0  # TODO: change to option_change when available
                            )
                            option_change_pct = (
                                0.0  # TODO: change to option_change_pct when available
                            )

                            market_value = (
                                option_value * position.open_qty * MULTIPLIER * fx_rate
                            )
                            breakeven_price = (
                                position.acb_per_sh / (fx_rate * MULTIPLIER)
                                if fx_rate > 0.0
                                else 0.0
                            )
                            distance_to_breakeven = (
                                (option_value - breakeven_price) / breakeven_price
                                if breakeven_price != 0.0
                                else 0.0
                            )
                            intraday_change = (
                                option_change * position.open_qty * MULTIPLIER * fx_rate
                            )
                            intraday_change_pct = option_change_pct

                    # total gain
                    gain = market_value - position.book_value

                    gain_pct = (
                        (market_value - position.book_value) / position.book_value
                        if position.book_value != 0.0
                        else 0.0
                    )

                    fx_exposure = (
                        market_value - (market_value / fx_rate)
                        if fx_rate != 1.0
                        else 0.0
                    )

                    holding = Holding(
                        symbol=security.quote.symbol,
                        account=position.account,
                        name=security.quote.name,
                        exchange=security.quote.exchange,
                        open=security.quote.open,
                        high=security.quote.high,
                        low=security.quote.low,
                        close=close,
                        currency=currency,
                        volume=security.quote.volume,
                        change=security.quote.change,
                        change_percent=security.quote.change_percent,
                        previous_close=security.quote.previousClose,
                        timestamp=security.quote.timestamp,
                        holding_category=position.category,
                        security_type=(
                            security.profile.type
                            if security.profile
                            else SecurityType.UNKNOWN
                        ),
                        fx_rate=fx_rate,
                        option_osi=position.option_osi,
                        open_date=position.open_date,
                        option_expiry=position.option_expiry,
                        option_strike=position.option_strike,
                        option_value=option_value,
                        option_change=option_change,
                        option_change_pct=option_change_pct,
                        option_dte=option_dte,
                        option_expired=option_expired,
                        open_qty=position.open_qty,
                        breakeven_price=breakeven_price,
                        book_value=position.book_value,
                        market_value=market_value,
                        gain=gain,
                        gain_pct=gain_pct,
                        weight=0.0,
                        intraday_change=intraday_change,
                        intraday_change_pct=intraday_change_pct,
                        distance_to_breakeven=distance_to_breakeven,
                        fx_exposure=fx_exposure,
                        pnl_contribution=0.0,
                        intraday_contribution=0.0,
                        days_held=days_held,
                    )
                    # Options are keyed by OSI so a stock and an option (or two
                    # option contracts) on the same underlying coexist.
                    key = position.option_osi or security.quote.symbol
                    if multi_account:
                        key = f"{position.account}|{key}"
                    self.holdings[key] = holding
        except Exception as e:
            logger.error(f"Error in _build_holdings: {e}", exc_info=True)
            return

        # Calculate quick attributes
        self.book_value = sum(h.book_value for h in self.holdings.values())
        self.market_value = sum(h.market_value for h in self.holdings.values())
        self.total_value = self.market_value + self.cash_balance
        self.cash_pct = (
            self.cash_balance / self.total_value if self.total_value else 0.0
        )

        self.unrealized_gain = self.market_value - self.book_value
        self.return_on_cost = (
            self.unrealized_gain / self.book_value if self.book_value else 0.0
        )
        self.return_on_value = (
            self.unrealized_gain / self.total_value if self.total_value else 0.0
        )
        self.pnl_intraday = sum(h.intraday_change for h in self.holdings.values())

        # Calculate weight by market value of each holding in the portfolio
        if self.total_value > 0:
            for holding in self.holdings.values():
                holding.weight = holding.market_value / self.total_value
                holding.pnl_contribution = holding.gain / self.total_value
                holding.intraday_contribution = (
                    holding.intraday_change / self.total_value
                )

    def _steady_assets(self) -> list[SteadyAsset]:
        """Fixed-income holdings as inputs to the portfolio series."""
        assets = []
        for key, lot in self._fixed_income_lots.items():
            terms = lot.terms
            assets.append(
                SteadyAsset(
                    weight=self.holdings[key].weight,
                    growth=(
                        partial(accrual_index, terms)
                        if terms is not None
                        else _flat_growth
                    ),
                )
            )
        return assets

    def _build_indicators(self) -> None:
        try:
            # Aggregate weights per quote symbol, aligned to self.securities order —
            # holdings may have several entries per symbol (stock + options), and
            # options proxy their weight through the underlying's close series.
            weights = [
                sum(h.weight for h in self.holdings.values() if h.symbol == sym)
                for sym in self.securities
            ]
            args = (list(self.securities.values()), np.array(weights, dtype=float))
            steady = self._steady_assets()
            frames = (
                compute_portfolio_timeseries_indicators(*args, steady)
                if steady
                else compute_portfolio_timeseries_indicators(*args)
            )
            self.indicators_df = frames[0]  # always return the first PORTF dataframe
            idf = self.indicators_df.rename_axis("date").reset_index()
            idf_safe = idf.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            ind_records = idf_safe.to_dict(orient="records")
            self.indicators = [
                TimeseriesIndicator.model_construct(**r) for r in ind_records
            ]
        except Exception as e:
            logger.error(f"Error in building portfolio indicators: {e}", exc_info=True)
            return

    def _build_metrics(self) -> None:
        try:
            metrics_df = compute_performance_metrics(self.indicators_df, self.rf_rate)
            if metrics_df.empty:
                return
            mdf = metrics_df.rename_axis("symbol").reset_index()
            met_records = mdf.to_dict(orient="records")
            self.metrics = PerformanceMetric.model_construct(
                # symbol="PORTF",
                name="Portfolio",
                exchange="N/A",
                currency="CAD",
                **met_records[0],
            )
        except Exception as e:
            logger.error(f"Error in building portfolio metrics: {e}", exc_info=True)
            return

    def _compute_mwrr(self) -> None:
        try:
            if not self.external_cash_flows or self.total_value <= 0:
                return

            today = date.today()
            n = len(self.external_cash_flows)

            # net_investment: contributions +ve, withdrawals -ve → sum = net capital in
            self.net_investment = sum(
                float(cf.amount) for cf in self.external_cash_flows
            )

            # Sort flows by date, then append the terminal cash outflow (liquidation value)
            flows = sorted(self.external_cash_flows, key=lambda cf: cf.transaction_date)

            t0 = flows[0].transaction_date
            times = np.empty(n + 1, dtype=float)
            amounts = np.empty(n + 1, dtype=float)
            for i, cf in enumerate(flows):
                times[i] = (cf.transaction_date - t0).days / 365.0
                amounts[i] = float(cf.amount)
            times[n] = (today - t0).days / 365.0
            amounts[n] = -self.total_value  # cash out to investor today

            # IRR requires at least one sign change
            if not (np.any(amounts > 0) and np.any(amounts < 0)):
                return

            # Precompute once — constant across Newton iterations
            neg_t_amounts = -times * amounts

            r = 0.10
            solved = False
            for _ in range(100):
                inv_r1 = 1.0 + r
                inv_factors = inv_r1 ** (-times)  # (1+r)^(-t), one pow per iter
                npv_val = float(np.dot(amounts, inv_factors))
                dnpv_val = float(np.dot(neg_t_amounts, inv_factors)) / inv_r1
                if abs(dnpv_val) < 1e-12:
                    break  # degenerate derivative — no valid IRR solution
                r_new = max(r - npv_val / dnpv_val, -0.9999)
                if abs(r_new - r) < 1e-10:
                    r = r_new
                    solved = True
                    break
                r = r_new
            if solved:
                self.mwrr = r
        except Exception as e:
            logger.error(f"Error computing MWRR: {e}", exc_info=True)

    def _build_correlation_matrix(self) -> None:
        if not self.securities:
            return
        try:
            stats = compute_return_statistics(list(self.securities.values()))
            self.covariance_matrix_df = stats.covariance
            self.return_observations = stats.observations

            # Correlations from a handful of returns are noise; leave those
            # symbols out and name them instead
            counts = stats.observations.reindex(stats.correlation.columns).fillna(0)
            keep = [s for s in stats.correlation.columns if counts[s] >= MIN_RETURN_OBS]
            excluded = sorted(s for s in stats.correlation.columns if s not in keep)
            corr = stats.correlation.loc[keep, keep]
            self.correlation_matrix_df = corr

            if len(keep) < 2:
                if excluded:
                    self.correlation_matrix = CorrelationMatrixDTO(
                        symbols=keep, excluded=excluded
                    )
                return

            stacked = corr.stack(future_stack=True)
            stacked.name = "value"
            entries_df = stacked.reset_index().rename(
                columns={"level_0": "row", "level_1": "col"}
            )

            self.correlation_matrix = CorrelationMatrixDTO(
                symbols=list(corr.columns),
                entries=[CorrelationEntry(**r) for r in entries_df.to_dict("records")],
                excluded=excluded,
            )
        except Exception as e:
            logger.error(
                f"Error in building portfolio correlation matrix: {e}", exc_info=True
            )
            return

    def build(self) -> None:
        if self.positions:
            self._build_holdings()
            self._build_indicators()
            self._build_metrics()
            self._build_correlation_matrix()
        self._compute_mwrr()
