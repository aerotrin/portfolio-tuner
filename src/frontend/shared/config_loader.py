from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator
import yaml

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
        yaml_path = Path(__file__).parent / "symbols.yml"

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
