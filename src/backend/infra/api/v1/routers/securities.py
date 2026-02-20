from __future__ import annotations
from datetime import date
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.application.use_cases.market_data import MarketDataManager
from backend.domain.entities.security import (
    Bar,
    PerformanceMetric,
    Profile,
    Quote,
    TimeseriesIndicator,
)
from backend.infra.api.v1.dependencies.auth import verify_token
from backend.infra.db.repo import SqliteMarketDataRepository

router = APIRouter(dependencies=[Depends(verify_token)])


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


# -----------------------------
# Request models
# -----------------------------
class SymbolsRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)


class BatchBarsRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start_date: date | None = None
    end_date: date | None = None


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
# Endpoints
# -----------------------------
@router.get(
    "/securities",
    response_model=List[str],
)
def get_available_symbols(
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """List all security symbols that have cached data in the system."""
    try:
        symbols = market_man.get_available_symbols()
        return symbols
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/securities/{symbol}",
    response_model=Quote,
)
def get_security_quote(
    symbol: str,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get the latest quote (price, volume, etc.) for a security by symbol."""
    try:
        quote = market_man.get_security_quote(symbol) or market_man.fetch_quote(symbol)

        if not quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Quote not found for symbol '{symbol}'.",
            )

        return quote

    except HTTPException:
        raise
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/securities/{symbol}/profile",
    response_model=Profile,
)
def get_security_profile(
    symbol: str,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get the company profile (name, sector, description, etc.) for a security."""
    try:
        profile = market_man.get_security_profile(symbol)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile not found for symbol '{symbol}'.",
            )
        return profile
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/securities/{symbol}/bars",
    response_model=List[Bar],
)
def get_security_bars(
    symbol: str,
    start_date: date | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: date | None = Query(default=None, description="YYYY-MM-DD"),
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get OHLCV historical bars for a security. Provide both start_date and end_date, or neither."""
    # If one date is supplied, require the other (prevents ambiguous range behavior)
    if (start_date is None) ^ (end_date is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide both start_date and end_date, or neither.",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be <= end_date.",
        )

    try:
        return market_man.get_security_bars(symbol, start_date, end_date)
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/securities/{symbol}/metrics",
    response_model=PerformanceMetric,
)
def get_security_metrics(
    symbol: str,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get performance metrics (returns, volatility, etc.) for a security."""
    try:
        metrics = market_man.get_security_metrics(symbol)
        if not metrics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metrics not found for symbol '{symbol}'.",
            )
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_error(e)


@router.get(
    "/securities/{symbol}/indicators",
    response_model=List[TimeseriesIndicator],
)
def get_security_indicators(
    symbol: str,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get timeseries indicators (e.g. price history) for a security."""
    try:
        indicators = market_man.get_security_indicators(symbol)
        if not indicators:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Indicators not found for symbol '{symbol}'.",
            )
        return indicators
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/securities/batch-quotes",
    response_model=List[Quote],
)
def get_security_batch_quotes(
    payload: SymbolsRequest,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get quotes for multiple securities in a batch request."""
    try:
        return market_man.get_security_quotes(payload.symbols)
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/securities/batch-profiles",
    response_model=List[Profile],
)
def get_security_batch_profiles(
    payload: SymbolsRequest,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get profiles for multiple securities in a batch request."""
    try:
        return market_man.get_security_profiles(payload.symbols)
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/securities/batch-bars",
    response_model=Dict[str, List[Bar]],
)
def get_security_batch_bars(
    payload: BatchBarsRequest,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get OHLCV bars for multiple securities in a batch request."""
    if (payload.start_date is None) ^ (payload.end_date is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide both start_date and end_date, or neither.",
        )

    if (
        payload.start_date
        and payload.end_date
        and payload.start_date > payload.end_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be <= end_date.",
        )

    try:
        return market_man.get_security_batch_bars(
            payload.symbols,
            payload.start_date,
            payload.end_date,
        )
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/securities/batch-metrics",
    response_model=List[PerformanceMetric],
)
def get_security_batch_metrics(
    payload: SymbolsRequest,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get performance metrics for multiple securities in a batch request."""
    try:
        return market_man.get_security_batch_metrics(payload.symbols)
    except Exception as e:
        _raise_http_error(e)


@router.post(
    "/securities/batch-indicators",
    response_model=Dict[str, List[TimeseriesIndicator]],
)
def get_security_batch_indicators(
    payload: SymbolsRequest,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    """Get timeseries indicators for multiple securities in a batch request."""
    try:
        return market_man.get_security_batch_indicators(payload.symbols)
    except Exception as e:
        _raise_http_error(e)
