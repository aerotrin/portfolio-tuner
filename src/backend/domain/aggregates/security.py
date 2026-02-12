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
            bars_df = pd.DataFrame([bar.model_dump() for bar in self.bars])
            bars_df = bars_df.sort_values(by="date", ascending=True).set_index("date")

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
