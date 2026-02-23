from datetime import date
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.application.use_cases.account import AccountManager
from backend.application.use_cases.market_data import MarketDataManager
from backend.application.use_cases.portfolio import PortfolioManager
from backend.domain.aggregates.portfolio import PortfolioSnapshotDTO
from backend.domain.entities.account import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    AccountRecordsDTO,
    Transaction,
    TransactionCreateDTO,
)
from backend.infra.api.v1.dependencies.auth import get_current_user_id, verify_token
from backend.infra.api.v1.dependencies.db import get_user_db
from backend.infra.db.repo import PgAccountDataRepository, PgMarketDataRepository

router = APIRouter(dependencies=[Depends(verify_token)])


# -----------------------------
# Dependencies
# -----------------------------
def get_account_manager(
    request: Request,
    db: Session = Depends(get_user_db),
) -> AccountManager:
    importer = request.app.state.records_importer
    repo = PgAccountDataRepository(db)
    return AccountManager(importer=importer, db=repo)


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
    account_man: AccountManager = Depends(get_account_manager),
    market_man: MarketDataManager = Depends(get_market_data_manager),
) -> PortfolioManager:
    return PortfolioManager(account_man=account_man, market_man=market_man)


def get_account_entity(
    account_id: UUID,
    account_man: AccountManager = Depends(get_account_manager),
) -> AccountEntity:
    """Resolve account_id to AccountEntity; raise 404 if not found."""
    account = account_man.read_account(str(account_id))
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


@router.post(
    "/accounts",
    response_model=AccountEntity,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    payload: AccountCreateRequest,
    user_id: str = Depends(get_current_user_id),
    account_man: AccountManager = Depends(get_account_manager),
):
    """Create a new brokerage account. The owner is always set to the authenticated user."""
    try:
        return account_man.create_account(payload, owner=user_id)
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts",
    response_model=List[AccountEntity],
)
def read_accounts_list(
    account_man: AccountManager = Depends(get_account_manager),
):
    """List all brokerage accounts."""
    try:
        return account_man.list_accounts()
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}",
    response_model=AccountEntity,
)
def read_account_details(
    account_id: UUID,
    account_man: AccountManager = Depends(get_account_manager),
):
    """Get full details for a single account by ID."""
    try:
        return account_man.read_account(str(account_id))
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
    """Partially update an account by ID."""
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
    """Delete an account and its associated data by ID."""
    try:
        account_man.delete_account(str(account_id))
        return None
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/transactions",
    response_model=List[Transaction],
)
def read_account_transactions(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    """List all transaction records for an account."""
    try:
        transactions = account_man.read_account_transactions(account.number)
        return transactions
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/accounts/{account_id}/transactions",
    response_model=Transaction,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    payload: TransactionCreateDTO,
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    """Add a new transaction (buy, sell, EFT, etc.) to an account."""
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
    """Delete a transaction from an account by transaction ID."""
    try:
        account_man.delete_transaction(account.number, transaction_id)
        return  # 204 No Content
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/records",
    response_model=AccountRecordsDTO,
)
def get_account_records(
    account: AccountEntity = Depends(get_account_entity),
    account_man: AccountManager = Depends(get_account_manager),
):
    """Get transactions, closed lots, and cash flows in a single request."""
    try:
        return account_man.get_account_records(account.number, None)
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/accounts/{account_id}/portfolio",
    response_model=PortfolioSnapshotDTO,
)
async def get_portfolio(
    account: AccountEntity = Depends(get_account_entity),
    portfolio_man: PortfolioManager = Depends(get_portfolio_manager),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    """Get full portfolio snapshot (summary, holdings, metrics, indicators, correlation) in a single request."""
    try:
        return await portfolio_man.get_portfolio(
            account.number, None, start_date, end_date
        )
    except Exception as e:
        _raise_http_error(e)
