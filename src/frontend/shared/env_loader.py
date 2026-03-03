from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (portfolio-tuner)
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_ENV_FILE = _ROOT / ".env"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",  # .env has both backend + frontend vars; ignore the rest
    )

    project_name: str = "PortfolioTuner"
    api_prefix: str = "/api/v1"

    backend_url: str = "http://127.0.0.1:8000"

    log_level: str = "WARNING"
    debug: bool = False
    connect_timeout: int = 5  # seconds
    read_timeout: int = 30  # seconds
    app_refresh_interval: int = 120_000  # ms

    # Supabase auth
    supabase_url: str = ""
    supabase_key: str = ""

    @property
    def api_url(self) -> str:
        return f"{self.backend_url}{self.api_prefix}"


config = Config()
