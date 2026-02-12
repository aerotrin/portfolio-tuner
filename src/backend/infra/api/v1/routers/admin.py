from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Literal
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.params import Body
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.application.use_cases.account import AccountManager
from backend.application.use_cases.market_data import MarketDataManager
from backend.domain.entities.security import GlobalRates
from backend.infra.db.repo import (
    SqliteAccountDataRepository,
    SqliteMarketDataRepository,
)
from backend.shared.config import config

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cooldown configuration
# ---------------------------------------------------------------------------
_COOLDOWN = timedelta(seconds=3)
_LAST_REFRESH: datetime | None = None  # module-level state

# ---------------------------------------------------------------------------
# Simple in-memory job model + registry
# ---------------------------------------------------------------------------
JobStatus = Literal["pending", "running", "success", "error"]


@dataclass
class RefreshJob:
    id: str
    symbols: list[str]
    intraday: bool
    status: JobStatus = "pending"
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    symbols_remaining: int = field(init=False)

    def __post_init__(self):
        """Initialize symbols_remaining to the total number of symbols."""
        object.__setattr__(self, "symbols_remaining", len(self.symbols))


_JOBS: dict[str, RefreshJob] = {}


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------
class RefreshJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    symbols: list[str]
    intraday: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    symbols_total: int
    symbols_remaining: int
    symbols_completed: int
    progress_percent: int
    progress_ratio: float


class RefreshSecuritiesResponse(BaseModel):
    status: str
    job_id: str | None = None
    symbols: list[str] | None = None
    intraday: bool | None = None
    reason: str | None = None
    cooldown_seconds_remaining: float | None = None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_db(request: Request):
    SessionLocal = request.app.state.SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_account_manager(
    request: Request,
    session: Session = Depends(get_db),
) -> AccountManager:
    importer = request.app.state.records_importer
    repo = SqliteAccountDataRepository(session)
    return AccountManager(importer=importer, db=repo)


def get_market_data_manager(
    request: Request,
    session: Session = Depends(get_db),
) -> MarketDataManager:
    repo = SqliteMarketDataRepository(session)
    return MarketDataManager(
        ds_us=request.app.state.fmp_client,
        ds_ca=request.app.state.eodhd_client,
        db=repo,
    )


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


# ---------------------------------------------------------------------------
# Simple synchronous admin endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/rates",
    response_model=GlobalRates,
)
def get_global_rates(
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    try:
        rates = market_man.get_global_rates()
        if rates is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Global rates not available.",
            )
        return rates
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_error(e)


@router.post("/admin/import-account", status_code=status.HTTP_202_ACCEPTED)
async def import_account(
    account_id: str = Form(...),
    file: UploadFile = File(...),
    account_man: AccountManager = Depends(get_account_manager),
):
    """Import transactions from an uploaded xlsx file. Must contain a sheet with a name that matches the account's number. Pass account_id (UUID)."""
    if file.filename and not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an xlsx spreadsheet.",
        )
    try:
        account = account_man.get_account(account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found.",
            )
        file_bytes = await file.read()
        account_man.import_account(account.number, file_bytes)
        return  # 202 Accepted
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_error(e)


@router.post("/admin/refresh-rates", status_code=status.HTTP_202_ACCEPTED)
def refresh_rates(
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    try:
        market_man.refresh_global_rates()
        return  # 202 Accepted
    except Exception as e:
        _raise_http_error(e)


@router.post("/admin/refresh-security", status_code=status.HTTP_202_ACCEPTED)
def refresh_security(
    symbol: str,
    market_man: MarketDataManager = Depends(get_market_data_manager),
):
    try:
        market_man.refresh_security(symbol)
        return  # 202 Accepted
    except Exception as e:
        _raise_http_error(e)


# ---------------------------------------------------------------------------
# Background worker for securities refresh
# NOTE: This is async because MarketDataManager uses async methods.
# ---------------------------------------------------------------------------
async def _run_refresh_job(
    job_id: str,
    app,
    symbols: list[str],
    intraday: bool,
) -> None:
    """Runs in a background task after the HTTP response is sent."""
    job = _JOBS.get(job_id)
    if not job:
        logger.warning("Refresh job %s not found in registry", job_id)
        return

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)

    SessionLocal = app.state.SessionLocal
    db = SessionLocal()
    try:
        repo = SqliteMarketDataRepository(db)
        market_man = MarketDataManager(
            ds_us=app.state.fmp_client,
            ds_ca=app.state.eodhd_client,
            db=repo,
        )

        market_man.refresh_global_rates()

        # Create progress callback that decrements symbols_remaining
        def on_progress(symbol: str):
            """Callback to update job progress after each symbol is processed."""
            if job.symbols_remaining > 0:
                job.symbols_remaining -= 1

        if intraday:
            logger.info(
                "Background INTRADAY securities refresh started, job_id=%s, symbols=%d",
                job_id,
                len(symbols),
            )
            await market_man.refresh_securities_intraday_async(
                symbols,
                max_concurrency=config.max_concurrency,
                on_progress=on_progress,
            )
        else:
            logger.info(
                "Background EOD securities refresh started, job_id=%s, symbols=%d",
                job_id,
                len(symbols),
            )
            await market_man.refresh_securities_async(
                symbols,
                start_date=None,
                end_date=None,
                max_concurrency=config.max_concurrency,
                on_progress=on_progress,
            )

        job.status = "success"
        logger.info("Background refresh job %s completed successfully", job_id)

    except Exception as e:
        logger.exception("Error in background refresh job %s", job_id)
        job.status = "error"
        job.error = str(e)

    finally:
        job.finished_at = datetime.now(timezone.utc)
        db.close()


# ---------------------------------------------------------------------------
# Async / background securities refresh endpoint with job ID
# ---------------------------------------------------------------------------
@router.post(
    "/admin/refresh-securities",
    response_model=RefreshSecuritiesResponse,
)
async def refresh_securities_async(
    request: Request,
    symbols: list[str] = Body(...),
    intraday: bool = False,
    bg_task: BackgroundTasks = None,
):
    """
    Trigger a background refresh of securities. Added cooldown prevents hammering.
    """
    global _LAST_REFRESH

    if bg_task is None:
        bg_task = BackgroundTasks()

    now = datetime.now(timezone.utc)

    # --- Cooldown to prevent hammering ---
    if _LAST_REFRESH and now - _LAST_REFRESH < _COOLDOWN:
        wait = _COOLDOWN - (now - _LAST_REFRESH)
        logger.info(
            "Skipping securities refresh; in cooldown (%.1fs remaining)",
            wait.total_seconds(),
        )
        return RefreshSecuritiesResponse(
            status="skipped",
            reason="cooldown",
            cooldown_seconds_remaining=round(wait.total_seconds(), 1),
        )

    _LAST_REFRESH = now

    # --- Create job object ---
    job_id = str(uuid.uuid4())
    job = RefreshJob(
        id=job_id,
        symbols=list(symbols),
        intraday=intraday,
    )
    _JOBS[job_id] = job

    # --- Schedule background work ---
    app = request.app
    bg_task.add_task(
        _run_refresh_job,
        job_id,
        app,
        list(symbols),
        intraday,
    )

    logger.info(
        "Scheduled %s securities refresh job_id=%s for %d symbols",
        "intraday" if intraday else "EOD",
        job_id,
        len(symbols),
    )

    return RefreshSecuritiesResponse(
        status="accepted",
        job_id=job_id,
        symbols=symbols,
        intraday=intraday,
    )


# ---------------------------------------------------------------------------
# Job status endpoint
# ---------------------------------------------------------------------------
@router.get(
    "/jobs/{job_id}",
    response_model=RefreshJobResponse,
)
def get_refresh_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    symbols_total = len(job.symbols)
    symbols_completed = symbols_total - job.symbols_remaining
    progress_percent = (
        (symbols_completed / symbols_total * 100) if symbols_total > 0 else 0
    )
    progress_percent = max(0, min(progress_percent, 100))
    progress_ratio = symbols_completed / symbols_total if symbols_total else 0.0

    return RefreshJobResponse(
        job_id=job.id,
        status=job.status,
        symbols=job.symbols,
        intraday=job.intraday,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        symbols_total=symbols_total,
        symbols_remaining=job.symbols_remaining,
        symbols_completed=symbols_completed,
        progress_percent=int(progress_percent),
        progress_ratio=progress_ratio,
    )
