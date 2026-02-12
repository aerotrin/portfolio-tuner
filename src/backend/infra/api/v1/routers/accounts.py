from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.application.use_cases.account import AccountManager
from backend.application.use_cases.market_data import MarketDataManager
from backend.application.use_cases.portfolio import PortfolioManager
from backend.domain.aggregates.portfolio import (
    CorrelationMatrixDTO,
    PortfolioSummaryDTO,
)
from backend.domain.entities.account import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    AccountSummaryDTO,
    CashFlow,
    ClosedLot,
    Holding,
    OpenLot,
    Transaction,
    TransactionCreateDTO,
)
from backend.domain.entities.security import PerformanceMetric, TimeseriesIndicator
from backend.infra.db.repo import (
    SqliteAccountDataRepository,
    SqliteMarketDataRepository,
)

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


def get_account_entity(
    account_id: UUID,
    account_man: AccountManager = Depends(get_account_manager),
) -> AccountEntity:
    """Resolve account_id to AccountEntity; raise 404 if not found."""
    account = account_man.get_account(str(account_id))
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found.",
        )
    return account


# -----------------------------
# Helpers
# -----------------------------
def _raise_http_error(exc: Exception) -> None:
    """
    Minimal, pragmatic exception mapping.
    Replace/extend with your domain exception types if you have them.
    """
    # Conflict (e.g. duplicate account number)
    if isinstance(exc, ValueError) and "already exists" in str(exc).lower():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

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


# --- Account CRUD ---
@router.post(
    "/accounts",
    response_model=AccountEntity,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    payload: AccountCreateRequest,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        return account_man.create_account(payload)
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts",
    response_model=List[AccountEntity],
)
def get_accounts_list(
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        return account_man.list_accounts()
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}",
    response_model=AccountEntity,
)
def get_account_details(
    account_id: UUID,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        return account_man.get_account(str(account_id))
    except Exception as e:
        _raise_http_error(e)


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountEntity,
)
def patch_account(
    account_id: UUID,
    payload: AccountPatchRequest,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        return account_man.patch_account(str(account_id), payload)
    except Exception as e:
        _raise_http_error(e)


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_account(
    account_id: UUID,
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        account_man.delete_account(str(account_id))
        return None
    except Exception as e:
        _raise_http_error(e)


# --- Account by id (summary, transactions, positions, etc.) ---
@router.get(
    "/accounts/{account_id}/summary",
    response_model=AccountSummaryDTO,
)
def get_account_summary(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        summary = account_man.get_account_summary(account.number, None)
        return summary
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/transactions",
    response_model=List[Transaction],
)
def get_account_transactions(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        transactions = account_man.get_account_transactions(account.number, None)
        return transactions
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/accounts/{account_id}/transactions",
    response_model=Transaction,
    status_code=status.HTTP_201_CREATED,
)
def add_transaction(
    payload: TransactionCreateDTO,
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        tx = account_man.create_transaction(account.number, payload)
        return tx
    except Exception as e:
        _raise_http_error(e)


@router.delete(
    "/accounts/{account_id}/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_transaction(
    transaction_id: str,
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        account_man.delete_transaction(account.number, transaction_id)
        return  # 204 No Content
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/open",
    response_model=List[OpenLot],
)
def get_account_open_positions(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        open_positions = account_man.get_account_open_positions(account.number, None)
        return open_positions
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/closed",
    response_model=List[ClosedLot],
)
def get_account_closed_positions(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        closed_positions = account_man.get_account_closed_positions(
            account.number, None
        )
        return closed_positions
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/cash",
    response_model=List[CashFlow],
)
def get_account_cash_flows(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    try:
        cash_flows = account_man.get_account_cash_flows(account.number, None)
        return cash_flows
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/portfolio",
    response_model=PortfolioSummaryDTO,
)
def get_account_portfolio_summary(
    account: AccountEntity = Depends(get_account_entity),
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        summary = portfolio_man.get_portfolio_summary(account.number, None)
        return summary
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/portfolio/holdings",
    response_model=dict[str, Holding],
)
def get_portfolio_holdings(
    account: AccountEntity = Depends(get_account_entity),
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        holdings = portfolio_man.get_portfolio_holdings(account.number, None)
        return holdings
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/portfolio/indicators",
    response_model=List[TimeseriesIndicator],
)
def get_portfolio_indicators(
    account: AccountEntity = Depends(get_account_entity),
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        indicators = portfolio_man.get_portfolio_indicators(account.number, None)
        return indicators
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/portfolio/metrics",
    response_model=PerformanceMetric,
)
def get_portfolio_metrics(
    account: AccountEntity = Depends(get_account_entity),
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        metrics = portfolio_man.get_portfolio_metrics(account.number, None)
        return metrics
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/portfolio/correlation",
    response_model=CorrelationMatrixDTO,
)
def get_portfolio_correlation_matrix(
    account: AccountEntity = Depends(get_account_entity),
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
):
    try:
        correlation_matrix = portfolio_man.get_portfolio_correlation_matrix(
            account.number, None
        )
        if correlation_matrix is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Correlation matrix not available. Portfolio may have insufficient data.",  # noqa: E501
            )
        return correlation_matrix
    except Exception as e:
        _raise_http_error(e)
