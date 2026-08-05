from pathlib import Path
import re
from typing import Any

from pydantic import (
    BaseModel,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
import yaml

# Project root (portfolio-tuner)
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_SYMBOLS_FILE = _ROOT / "symbols.yml"

# Facet taxonomy ----------------------------------------------------------------

# `type` and `region` are optional in symbols.yml — the shipped example config and
# any pre-existing user config predate them, and a hard failure here would brick
# the app at bootstrap.
DEFAULT_TYPE = "Other"
DEFAULT_REGION = "Global"

# Known values, in the order their filter chips should appear. Values outside
# these lists are still accepted; they just sort to the end.
TYPE_ORDER = (
    "Equity",
    "Fixed Income",
    "Commodity",
    "Crypto",
    "Forex",
    "Multi-Asset",
    "Index",
    DEFAULT_TYPE,
)
REGION_ORDER = ("US", "Canada", "World", DEFAULT_REGION)


def facet_sort_key(value: str, order: tuple[str, ...]) -> tuple[int, str]:
    """Sort key placing known values first in declared order, unknowns last A-Z."""
    return (order.index(value), "") if value in order else (len(order), value)


def slugify(text: str) -> str:
    """'US Equity | Style & Factor' -> 'us-equity-style-factor'"""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


# Symbols loader ----------------------------------------------------------------


class SymbolGroup(BaseModel):
    label: str
    type: str = DEFAULT_TYPE
    region: str = DEFAULT_REGION
    symbols: tuple[str, ...] = tuple()  # immutable, hashable, nice for caching

    @property
    def key(self) -> str:
        """Identity of a group: region + type + label.

        `label` alone is not unique — it is the leaf under a region/type pair, so
        "Core" exists once per region. Everything that needs to name a single
        group (widget options, widget keys) uses this instead.
        """
        return slugify(f"{self.region} {self.type} {self.label}")

    @field_validator("label", mode="before")
    @classmethod
    def _clean_label(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise TypeError(f"'label' must be a string, got {type(v).__name__}: {v!r}")

        label = " ".join(v.split())
        if not label:
            raise ValueError("label must not be empty")
        return label

    @field_validator("type", "region", mode="before")
    @classmethod
    def _clean_facet(cls, v: Any, info: ValidationInfo) -> str:
        default = DEFAULT_TYPE if info.field_name == "type" else DEFAULT_REGION
        if v is None:
            return default
        if not isinstance(v, str):
            raise TypeError(
                f"'{info.field_name}' must be a string, got {type(v).__name__}: {v!r}"
            )
        # Case is preserved deliberately — title-casing would mangle e.g. "REITs".
        return " ".join(v.split()) or default

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

    @field_validator("benchmarks", "snapshot", mode="before")
    @classmethod
    def _accept_single_or_list(cls, v: Any) -> Any:
        """Allow these sections to be written as a list, like the market ones.

        They are one logical group, but writing every section the same way is
        easier to edit. A list is merged into a single group, keeping symbol
        order and dropping duplicates.
        """
        if not isinstance(v, (list, tuple)):
            return v

        groups = [SymbolGroup.model_validate(g) for g in v]
        if not groups:
            raise ValueError("must contain at least one group")

        merged = dict.fromkeys(s for g in groups for s in g.symbols)
        return groups[0].model_copy(update={"symbols": tuple(merged)})

    @model_validator(mode="after")
    def _unique_group_keys(self) -> "SymbolsConfig":
        # Labels may repeat across regions ("Core" under US, Canada and World);
        # the region/type/label triple is what has to stay unique, since it names
        # the group in the filter widgets and in their Streamlit keys.
        for field in ("base_market_etfs", "base_market_stocks"):
            seen: set[str] = set()
            for group in getattr(self, field):
                if group.key in seen:
                    raise ValueError(
                        f"{field}: duplicate group {group.label!r} for "
                        f"region {group.region!r} and type {group.type!r}"
                    )
                seen.add(group.key)
        return self


def load_symbols_config(yaml_path: Path | None = None) -> SymbolsConfig:
    if yaml_path is None:
        yaml_path = _DEFAULT_SYMBOLS_FILE

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Symbols configuration file not found: {yaml_path}\n"
            "Please ensure symbols.yml exists in the project root."
        )

    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    try:
        return SymbolsConfig.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Invalid symbols.yml:\n{e}") from e
