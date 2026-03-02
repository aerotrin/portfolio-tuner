from datetime import datetime, timezone
from typing import Any, List

import numpy as np
import pandas as pd
from pydantic import BaseModel

from backend.domain.aggregates.security import Security
from backend.domain.analytics.security import (
    compute_performance_metrics_batch,
    compute_portfolio_timeseries_indicators,
)
from backend.domain.entities.security import GlobalRates


class SimulatePortfolioRequest(BaseModel):
    symbols: List[str]
    n_p: int = 5000
    seed: int | None = None


class SimulationConfig(BaseModel):
    symbols: List[str]
    n_p: int
    seed: int | None = None
    run_at: datetime


class SimulatedPortfoliosDTO(BaseModel):
    config: SimulationConfig
    portfolios: list[dict[str, Any]]


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
        self.run_at: datetime | None = None

    def run(self):
        """Generate random portfolios and compute indicators & metrics."""
        self.run_at = datetime.now(timezone.utc)
        rng = np.random.default_rng(self.seed)
        weight_matrix = rng.dirichlet(np.ones(len(self.securities)), size=self.n_p)
        self.weight_matrix = weight_matrix
        self.timeseries = compute_portfolio_timeseries_indicators(
            self.securities, weight_matrix
        )
        self.performance = compute_performance_metrics_batch(
            self.timeseries, self.rf_rate
        )

    def _build_record(
        self, i: int, port_id: str, row: pd.Series, symbols: list[str]
    ) -> dict[str, Any]:
        record: dict[str, Any] = {"id": port_id}
        record.update(row.to_dict())
        record["weights"] = dict(zip(symbols, self.weight_matrix[i].tolist()))
        return record

    def find_optimal_portfolio(self) -> dict[str, Any]:
        """Find the portfolio with the highest Sharpe ratio and return a flat record."""
        if self.performance.empty:
            raise ValueError("No metrics computed. Run run_simulator() first.")

        best_id = str(self.performance["sharpe"].idxmax())
        best_idx = 0 if best_id == "PORTF" else int(best_id.split("_")[1])
        symbols = [s.quote.symbol for s in self.securities]
        return self._build_record(
            best_idx, best_id, self.performance.loc[best_id], symbols
        )

    def get_all_portfolios(self) -> list[dict[str, Any]]:
        """Return all simulated portfolios, each with flat metrics and a weights sub-dict."""
        if self.performance.empty:
            raise ValueError("No metrics computed. Run run() first.")

        symbols = [s.quote.symbol for s in self.securities]
        return [
            self._build_record(i, str(port_id), row, symbols)
            for i, (port_id, row) in enumerate(self.performance.iterrows())
        ]
