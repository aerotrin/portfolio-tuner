import logging
from typing import List

import numpy as np
import pandas as pd

from backend.domain.analytics.security import (
    compute_performance_metrics,
    compute_timeseries_indicators,
)
from backend.domain.entities.security import (
    Bar,
    GlobalRates,
    PerformanceMetric,
    Profile,
    Quote,
    TimeseriesIndicator,
)

logger = logging.getLogger(__name__)


class Security:
    """A security is composed of bars, quote and profile data."""

    def __init__(
        self,
        quote: Quote,
        bars: List[Bar],
        rates: GlobalRates,
        profile: Profile,
    ):
        self.quote = quote
        self.bars = bars
        self.profile = profile
        self.rf_rate = float(rates.rf_rate) / 100
        self.fx_rate = float(rates.fx_rate)

        self.indicators_df: pd.DataFrame = pd.DataFrame()  # keep for fast internal use
        self.indicators: List[TimeseriesIndicator] = []

        self.calculate()

    def calculate(self):
        try:
            quote_as_bar = Bar(
                symbol=self.quote.symbol,
                open=self.quote.open,
                high=self.quote.high,
                low=self.quote.low,
                close=self.quote.close,
                volume=self.quote.volume,
                date=self.quote.timestamp,
            )
            bars_df = pd.DataFrame(
                [bar.model_dump() for bar in self.bars + [quote_as_bar]]
            )
            bars_df["date"] = pd.to_datetime(bars_df["date"], utc=True).dt.normalize()
            bars_df = bars_df.drop_duplicates(subset="date", keep="last")
            bars_df = (
                bars_df.sort_values(by="date", ascending=True)
                .tail(252)
                .set_index("date")
            )

            self.bars = [
                Bar(**r) for r in bars_df.reset_index().to_dict(orient="records")
            ]

            self.indicators_df = compute_timeseries_indicators(bars_df)
            self.metrics_df = compute_performance_metrics(
                self.indicators_df, self.rf_rate
            )

            idf = self.indicators_df.rename_axis("date").reset_index()
            idf_safe = idf.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            ind_records = idf_safe.to_dict(orient="records")
            self.indicators = [
                TimeseriesIndicator.model_construct(**r) for r in ind_records
            ]

            mdf = self.metrics_df.rename_axis("symbol").reset_index()
            met_records = mdf.to_dict(orient="records")

            self.metrics = PerformanceMetric.model_construct(
                # symbol=self.quote.symbol,
                name=self.quote.name,
                exchange=self.quote.exchange,
                currency=self.quote.currency,
                **met_records[0],
            )
        except Exception as e:
            logger.error(
                f"Error in calculating security indicators and metrics: {e}",
                exc_info=True,
            )
            return
