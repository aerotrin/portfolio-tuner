from typing import Any, List

import numpy as np
import pandas as pd
from pydantic import BaseModel

from backend.domain.aggregates.security import Security
from backend.domain.analytics.security import (
    compute_performance_metrics,
    compute_portfolio_timeseries_indicators,
)
from backend.domain.entities.security import GlobalRates


class SimulatePortfolioRequest(BaseModel):
    symbols: List[str]
    n_p: int = 5000
    seed: int | None = None


class OptimalPortfolioDTO(BaseModel):
    id: str
    metrics: dict[str, Any]
    weights: dict[str, float]
    n_p: int
    seed: int | None = None


class SimPortfolios:
    """Efficiently simulate many portfolio configurations."""

    def __init__(
        self,
        securities: list[Security],
        rates: GlobalRates,
        n_p: int,
        seed: int | None = None,
    ):
        self.securities = securities
        self.rf_rate = float(rates.rf_rate) / 100
        self.fx_rate = float(rates.fx_rate)
        self.n_p = n_p
        self.seed = seed

        self.timeseries: List[pd.DataFrame] = []
        self.performance: pd.DataFrame = pd.DataFrame()
        self.weight_matrix: np.ndarray = np.array([])

    def run(self):
        """Generate random portfolios and compute indicators & metrics."""
        rng = np.random.default_rng(self.seed)
        weight_matrix = rng.dirichlet(np.ones(len(self.securities)), size=self.n_p)
        self.weight_matrix = weight_matrix
        self.timeseries = compute_portfolio_timeseries_indicators(
            self.securities, weight_matrix
        )
        self.performance = pd.concat(
            [compute_performance_metrics(df, self.rf_rate) for df in self.timeseries]
        )  # TODO: improve performance by using vectorized operations

    def find_optimal_portfolio(self) -> dict:
        """Find the portfolio with the highest Sharpe ratio and return its metrics and weights."""
        if self.performance.empty:
            raise ValueError("No metrics computed. Run run_simulator() first.")

        metrics_df = self.performance.copy()

        # Find the portfolio with the highest Sharpe ratio
        best_portfolio = metrics_df["sharpe"].idxmax()  # TODO: make this an arg
        best_metrics = metrics_df.loc[best_portfolio]

        # Map symbol to row index in weight matrix
        if best_portfolio == "PORTF":
            best_idx = 0
        else:
            best_idx = int(best_portfolio.split("_")[1])

        best_weights = self.weight_matrix[best_idx]

        result = {
            "id": best_portfolio,
            "metrics": best_metrics.to_dict(),
            "weights": dict(
                zip(
                    [s.quote.symbol for s in self.securities],
                    [float(w) for w in best_weights],
                )
            ),
        }
        return result
