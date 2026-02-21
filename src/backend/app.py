from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.adapters.eodhd_client import EODHDClient, EODHDConfig
from backend.infra.adapters.excel_pandas_client import ExcelPandasClient
from backend.infra.adapters.fmp_client import FMPClient, FMPConfig
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
        config.db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Client setup
    records_importer = ExcelPandasClient()
    fmp_client = FMPClient(
        FMPConfig(
            api_key=config.fmp_api_key,
            base_url=config.fmp_base_url,
            timeout_sec=config.fmp_timeout_sec,
            default_days_back=config.fmp_default_days_back,
            max_per_minute=config.fmp_max_per_minute,
            burst_capacity=config.fmp_burst_capacity,
            min_request_interval=config.fmp_min_request_interval,
        )
    )
    eodhd_client = EODHDClient(
        EODHDConfig(
            api_key=config.eodhd_api_key,
            base_url=config.eodhd_base_url,
            timeout_sec=config.eodhd_timeout_sec,
            default_days_back=config.eodhd_default_days_back,
        )
    )

    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    app.state.records_importer = records_importer
    app.state.fmp_client = fmp_client
    app.state.eodhd_client = eodhd_client

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
