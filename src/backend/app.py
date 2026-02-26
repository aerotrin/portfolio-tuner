from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.adapters.excel_pandas_client import ExcelPandasClient
from backend.infra.adapters.fmp_client import FMPClient, FMPConfig
from backend.infra.adapters.rate_limiter import RateLimiterConfig
from backend.infra.adapters.yfinance_client import YFinanceClient
from backend.infra.api.v1.routers import accounts as accounts_routers
from backend.infra.api.v1.routers import admin as admin_routers
from backend.infra.api.v1.routers import securities as securities_routers
from backend.shared.config import config
from backend.shared.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    logger.info("Starting up...")

    engine = create_engine(
        config.postgres_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Client setup
    records_importer = ExcelPandasClient()

    if config.enable_fmp_as_primary:
        primary_ds = FMPClient(
            FMPConfig(
                api_key=config.fmp_api_key,
                rate_limiter=RateLimiterConfig(max_per_minute=config.fmp_rate_limit),
            )
        )
        backup_ds = YFinanceClient()
    else:
        primary_ds = YFinanceClient()
        backup_ds = None

    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    app.state.records_importer = records_importer
    app.state.primary_market_datasource = primary_ds
    app.state.backup_market_datasource = backup_ds

    yield
    engine.dispose()
    logger.info("Shutting down...")


# FastAPI setup
app = FastAPI(lifespan=lifespan)
app.include_router(admin_routers.router, prefix=config.api_prefix)
app.include_router(accounts_routers.router, prefix=config.api_prefix)
app.include_router(securities_routers.router, prefix=config.api_prefix)


@app.get("/health")
def health():
    return {"status": "ok"}
