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
    backend_url: str = "http://127.0.0.1:8001"
    api_prefix: str = "/api/v1"

    # DB
    postgres_url: str = ""

    # FMP settings
    max_concurrency: int = 5
    enable_fmp_as_primary: bool = False
    fmp_api_key: str = Field(default="")
    fmp_rate_limit: int = 100

    # Logging
    log_level: str = "WARNING"

    # Supabase auth (ES256 / P-256 asymmetric signing)
    supabase_jwt_public_key: str = Field(default="")


config = Config()
