import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_validator
import yaml


def _config_dir() -> Path:
    """Config directory: CONFIG_DIR env if set, else <project_root>/config (parent of src/)."""
    if os.environ.get("CONFIG_DIR"):
        return Path(os.environ["CONFIG_DIR"])
    return Path(__file__).resolve().parents[3] / "config"


# Symbols loader ----------------------------------------------------------------


class SymbolGroup(BaseModel):
    label: str
    symbols: tuple[str, ...] = tuple()  # immutable, hashable, nice for caching

    @field_validator("symbols", mode="before")
    @classmethod
    def _clean_symbols(cls, v: Any) -> tuple[str, ...]:
        if not isinstance(v, (list, tuple)):
            raise TypeError(f"'symbols' must be a list, got {type(v).__name__}")

        cleaned: list[str] = []
        for s in v:
            if not isinstance(s, str):
                raise TypeError(
                    f"Symbol must be a string, got {type(s).__name__}: {s!r}"
                )
            sym = s.strip().upper()
            if sym:
                cleaned.append(sym)

        if not cleaned:
            raise ValueError("symbols must contain at least one non-empty symbol")

        return tuple(cleaned)


class SymbolsConfig(BaseModel):
    benchmarks: SymbolGroup
    snapshot: SymbolGroup
    base_market_etfs: list[SymbolGroup]
    base_market_stocks: list[SymbolGroup]


def load_symbols_config(yaml_path: Path | None = None) -> SymbolsConfig:
    if yaml_path is None:
        yaml_path = _config_dir() / "symbols.yml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Symbols configuration file not found: {yaml_path}\n"
            "Please ensure config/symbols.yml exists in the project root."
        )

    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    try:
        return SymbolsConfig.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Invalid symbols.yml:\n{e}") from e


# Accounts loader ----------------------------------------------------------------

TaxStatus = Literal["Registered", "Non-Registered"]


class Account(BaseModel):
    number: str
    owner: str
    type: str
    status: TaxStatus
    benchmark: str

    @field_validator("status", mode="before")
    @classmethod
    def _clean_status(cls, v: Any) -> TaxStatus:
        if not isinstance(v, str):
            raise TypeError(f"status must be a string, got {type(v).__name__}")

        s = v.strip().lower()
        if s == "registered":
            return "Registered"
        if s in {"non-registered", "non registered"}:
            return "Non-Registered"

        raise ValueError("status must be 'Registered' or 'Non-Registered'")

    @field_validator("benchmark", mode="before")
    @classmethod
    def _clean_benchmark(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise TypeError(f"benchmark must be a string, got {type(v).__name__}")
        return v.strip().upper()


class AccountsConfig(BaseModel):
    accounts: tuple[Account, ...]


def load_accounts_config(yaml_path: Path | None = None) -> AccountsConfig:
    if yaml_path is None:
        yaml_path = _config_dir() / "accounts.yml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Accounts configuration file not found: {yaml_path}\n"
            "Please ensure config/accounts.yml exists in the project root."
        )

    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    try:
        return AccountsConfig.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Invalid accounts.yml:\n{e}") from e
