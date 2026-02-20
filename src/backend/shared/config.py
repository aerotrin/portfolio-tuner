from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (portfolio-tuner)
_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ENV_FILE = _ROOT / ".env"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",  # .env has both backend + frontend vars; ignore the rest
    )

    project_name: str = "PortfolioTuner"
    backend_url: str = "http://127.0.0.1:8000"
    api_prefix: str = "/api/v1"

    admin_enabled: bool = False
    debug: bool = False

    max_concurrency: int = 10

    # DB
    db_url: str = "sqlite:///./data/dev.db"
    db_user: str = ""
    db_password: str = ""

    # FMP settings
    fmp_api_key: str = Field(default="")
    fmp_base_url: str = "https://financialmodelingprep.com/stable"
    fmp_timeout_sec: float = 10.0
    fmp_default_days_back: int = 365
    # -- rate limiting
    fmp_max_per_minute: int = 280
    fmp_burst_capacity: int = 50
    fmp_min_request_interval: float = 0.05

    # EODHD settings
    eodhd_api_key: str = Field(default="")
    eodhd_base_url: str = "https://eodhd.com/api"
    eodhd_timeout_sec: float = 10.0
    eodhd_default_days_back: int = 365

    # Supabase auth (ES256 / P-256 asymmetric signing)
    supabase_jwt_public_key: str = Field(default="")


config = Config()
