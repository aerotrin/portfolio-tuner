from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.use_cases.account import AccountManager
from src.application.use_cases.market_data import MarketDataManager
from src.application.use_cases.portfolio import PortfolioManager
from src.domain.aggregates.portfolio import CorrelationMatrixDTO, PortfolioSummaryDTO
from src.domain.entities.account import (
    AccountSummaryDTO,
    CashFlow,
    ClosedLot,
    Holding,
    OpenLot,
    Transaction,
    TransactionCreateDTO,
)
from src.domain.entities.security import PerformanceMetric, PortfolioIndicator
from src.infra.db.repo import SqliteAccountDataRepository, SqliteMarketDataRepository

router = APIRouter()


# -----------------------------
# Dependencies
# -----------------------------
def get_db(request: Request):
    SessionLocal = request.app.state.SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_account_manager(
    request: Request,
    db: Session = Depends(get_db),
) -> AccountManager:
    importer = request.app.state.records_importer
    repo = SqliteAccountDataRepository(db)
    return AccountManager(importer=importer, db=repo)


def get_market_data_manager(
    request: Request,
    db: Session = Depends(get_db),
) -> MarketDataManager:
    repo = SqliteMarketDataRepository(db)
    return MarketDataManager(
        ds_us=request.app.state.fmp_client,
        ds_ca=request.app.state.eodhd_client,
        db=repo,
    )


def get_portfolio_manager(
    account_man: AccountManager = Depends(get_account_manager),
    market_man: MarketDataManager = Depends(get_market_data_manager),
) -> PortfolioManager:
    return PortfolioManager(account_man=account_man, market_man=market_man)


# -----------------------------
# Helpers
# -----------------------------
def _raise_http_error(exc: Exception) -> None:
    """
    Minimal, pragmatic exception mapping.
    Replace/extend with your domain exception types if you have them.
    """
    # Common "bad request" cases
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Common "not found" cases (adapt to your domain exceptions if available)
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    # DB conflicts (unique constraint, FK, etc.)
    if isinstance(exc, IntegrityError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request conflicts with existing data.",
        )

    # Fallback
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected server error.",
    )


# -----------------------------
# Endpoints (Idiomatic REST)
# -----------------------------
@router.get(
    "/accounts/{account_number}",
    response_model=AccountSummaryDTO,
)
def get_account_summary(
    account_number: str,
    account_name: str | None = None,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        summary = account_man.get_account_summary(account_number, account_name)
        return summary
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/transactions",
    response_model=List[Transaction],
)
def get_account_transactions(
    account_number: str,
    account_name: str | None = None,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        transactions = account_man.get_account_transactions(
            account_number, account_name
        )
        return transactions
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/accounts/{account_number}/transactions",
    response_model=Transaction,
    status_code=status.HTTP_201_CREATED,
)
def add_transaction(
    account_number: str,
    payload: TransactionCreateDTO,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        tx = account_man.create_transaction(account_number, payload)
        return tx
    except Exception as e:
        _raise_http_error(e)


@router.delete(
    "/accounts/{account_number}/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_transaction(
    account_number: str,
    transaction_id: str,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        account_man.delete_transaction(account_number, transaction_id)
        return  # 204 No Content
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/open",
    response_model=List[OpenLot],
)
def get_account_open_positions(
    account_number: str,
    account_name: str | None = None,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        open_positions = account_man.get_account_open_positions(
            account_number, account_name
        )
        return open_positions
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/closed",
    response_model=List[ClosedLot],
)
def get_account_closed_positions(
    account_number: str,
    account_name: str | None = None,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        closed_positions = account_man.get_account_closed_positions(
            account_number, account_name
        )
        return closed_positions
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/cash",
    response_model=List[CashFlow],
)
def get_account_cash_flows(
    account_number: str,
    account_name: str | None = None,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        cash_flows = account_man.get_account_cash_flows(account_number, account_name)
        return cash_flows
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/portfolio",
    response_model=PortfolioSummaryDTO,
)
def get_account_portfolio_summary(
    account_number: str,
    account_name: str | None = None,
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        summary = portfolio_man.get_portfolio_summary(account_number, account_name)
        return summary
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/portfolio/holdings",
    response_model=dict[str, Holding],
)
def get_portfolio_holdings(
    account_number: str,
    account_name: str | None = None,
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        holdings = portfolio_man.get_portfolio_holdings(account_number, account_name)
        return holdings
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/portfolio/indicators",
    response_model=List[PortfolioIndicator],
)
def get_portfolio_indicators(
    account_number: str,
    account_name: str | None = None,
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        indicators = portfolio_man.get_portfolio_indicators(
            account_number, account_name
        )
        return indicators
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/portfolio/metrics",
    response_model=PerformanceMetric,
)
def get_portfolio_metrics(
    account_number: str,
    account_name: str | None = None,
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        metrics = portfolio_man.get_portfolio_metrics(account_number, account_name)
        return metrics
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_number}/portfolio/correlation",
    response_model=CorrelationMatrixDTO,
)
def get_portfolio_correlation_matrix(
    account_number: str,
    account_name: str | None = None,
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        correlation_matrix = portfolio_man.get_portfolio_correlation_matrix(
            account_number, account_name
        )
        if correlation_matrix is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Correlation matrix not available. Portfolio may have insufficient data.",  # noqa: E501
            )
        return correlation_matrix
    except Exception as e:
        _raise_http_error(e)
