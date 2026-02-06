from datetime import date, datetime
import logging
from typing import List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from src.domain.aggregates.security import Security
from src.domain.analytics.security import (
    compute_correlation_matrix,
    compute_performance_metrics,
    compute_portfolio_timeseries_indicators,
)
from src.domain.entities.account import Category, Holding, OpenLot
from src.domain.entities.security import (
    GlobalRates,
    PerformanceMetric,
    PortfolioIndicator,
)

logger = logging.getLogger(__name__)

MULTIPLIER = 100


class CorrelationEntry(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    row: str
    col: str
    value: float


class CorrelationMatrixDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    symbols: Optional[list[str]] = None
    entries: Optional[list[CorrelationEntry]] = None
    as_of: Optional[datetime] = None


class PortfolioSummaryDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    id: str
    book_value: float
    market_value: float
    total_value: float
    cash_balance: float
    cash_pct: float
    unrealized_gain: float
    return_on_cost: float
    return_on_value: float
    pnl_intraday: float
    open_positions: List[str]


class Portfolio:
    """A portfolio is composed of securities for a given set of open positions."""

    def __init__(
        self,
        id: str,
        cash: float,
        positions: List[OpenLot],
        securities: dict[str, Security],
        rates: GlobalRates,
    ):
        self.id = id
        self.cash_balance = cash
        self.positions = positions
        self.securities = securities
        self.rf_rate = float(rates.rf_rate or 0.0) / 100
        self.fx_rate = float(rates.fx_rate or 1.0)

        self.indicators_df: pd.DataFrame = pd.DataFrame()
        self.indicators: List[PortfolioIndicator] = []

        self.correlation_matrix_df: pd.DataFrame = pd.DataFrame()
        self.correlation_matrix: CorrelationMatrixDTO = CorrelationMatrixDTO()

        self.holdings: dict[str, Holding] = {}

        self.book_value: float = 0.0
        self.market_value: float = 0.0
        self.total_value: float = cash
        self.cash_pct: float = 1.0

        self.unrealized_gain: float = 0.0
        self.return_on_cost: float = 0.0
        self.return_on_value: float = 0.0
        self.pnl_intraday: float = 0.0

        self.metrics = PerformanceMetric(
            symbol="PORTF",
            name="Portfolio",
            exchange="N/A",
            currency="CAD",
        )

        self.build()

    def _build_holdings(self) -> None:
        try:
            for position in self.positions:
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
                            option_value = float(close) - float(
                                position.option_strike or 0.0
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
                            option_value = float(position.option_strike or 0.0) - float(
                                close
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
                    else:
                        market_value = position.book_value  # Fixed income
                        breakeven_price = 0.0
                        distance_to_breakeven = 0.0

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
                        security_type=security.profile.type,
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
                    self.holdings[security.quote.symbol] = holding
        except Exception as e:
            logger.error(f"Error in _build_holdings: {e}", exc_info=True)
            return

        # Calculate quick attributes
        self.book_value = sum(h.book_value for h in self.holdings.values())
        self.market_value = sum(h.market_value for h in self.holdings.values())
        self.total_value = self.market_value + self.cash_balance
        self.cash_pct = self.cash_balance / self.total_value

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

    def _build_indicators(self) -> None:
        weights = [h.weight for h in self.holdings.values()]
        self.indicators_df = compute_portfolio_timeseries_indicators(
            list(self.securities.values()), np.array(weights, dtype=float)
        )[0]  # always return the first PORTF dataframe
        idf = self.indicators_df.rename_axis("date").reset_index()
        idf_safe = idf.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        ind_records = idf_safe.to_dict(orient="records")
        self.indicators = [PortfolioIndicator.model_construct(**r) for r in ind_records]

    def _build_metrics(self) -> None:
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

    def _build_correlation_matrix(self) -> None:
        if not self.securities:
            return
        self.correlation_matrix_df = compute_correlation_matrix(
            list(self.securities.values())
        )
        corr = self.correlation_matrix_df

        # Validate matrix is not empty
        if corr.empty or len(corr.columns) == 0:
            return

        stacked = corr.stack(future_stack=True)
        stacked.name = "value"
        entries_df = stacked.reset_index().rename(
            columns={"level_0": "row", "level_1": "col"}
        )

        self.correlation_matrix = CorrelationMatrixDTO(
            symbols=list(corr.columns),
            entries=[CorrelationEntry(**r) for r in entries_df.to_dict("records")],
        )

    def build(self) -> None:
        if not self.positions:
            return
        self._build_holdings()
        self._build_indicators()
        self._build_metrics()
        self._build_correlation_matrix()
