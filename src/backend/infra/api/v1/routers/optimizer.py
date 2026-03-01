import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.application.use_cases.market_data import MarketDataManager
from backend.application.use_cases.simulator import PortfolioSimulatorManager
from backend.domain.aggregates.portfolio_simulator import (
    OptimalPortfolioDTO,
    SimulatePortfolioRequest,
)
from backend.infra.api.v1.dependencies.auth import verify_token
from backend.infra.api.v1.dependencies.db import get_user_db
from backend.infra.db.repo import PgMarketDataRepository

router = APIRouter(dependencies=[Depends(verify_token)])
logger = logging.getLogger(__name__)


# -----------------------------
# Dependencies
# -----------------------------
def get_market_data_manager(
    request: Request,
    db: Session = Depends(get_user_db),
) -> MarketDataManager:
    repo = PgMarketDataRepository(db)
    return MarketDataManager(
        ds_primary=request.app.state.primary_market_datasource,
        ds_backup=request.app.state.backup_market_datasource,
        db=repo,
    )


def get_portfolio_manager(
    market_man: MarketDataManager = Depends(get_market_data_manager),
) -> PortfolioSimulatorManager:
    # run_simulated_portfolio only uses market_man
    return PortfolioSimulatorManager(market_man=market_man)


# -----------------------------
# Endpoints
# -----------------------------
@router.post("/simulator/optimal", response_model=OptimalPortfolioDTO)
async def get_optimal_portfolio(
    payload: SimulatePortfolioRequest,
    portfolio_man: PortfolioSimulatorManager = Depends(get_portfolio_manager),
):
    """Run Monte Carlo portfolio simulation and return the optimal allocation."""
    try:
        result = await portfolio_man.get_optimal_portfolio(
            symbols=payload.symbols,
            n_p=payload.n_p,
        )
        return OptimalPortfolioDTO(**result)
    except Exception as e:
        logger.exception("Error in get_optimal_portfolio: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Optimal portfolio simulation failed.",
        )
