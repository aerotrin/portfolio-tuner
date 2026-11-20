from typing import TYPE_CHECKING, Any, Iterable, Mapping, NamedTuple, Optional

import numpy as np
import pandas as pd

from backend.domain.entities.account import Category, Holding
from backend.domain.entities.security import SecurityType

if TYPE_CHECKING:
    from backend.domain.aggregates.security import Security

CASH_LABEL = "Cash"
UNCLASSIFIED_LABEL = "Unclassified"
ETF_UNCLASSIFIED_LABEL = "ETF / unclassified"
DIMENSIONS = ("asset_type", "instrument", "sector", "country", "currency", "account")
OPTION_CATEGORIES = {Category.CALL_OPTION, Category.PUT_OPTION}

# Matches the minimum history required for a volatility estimate
MIN_RISK_OBS = 40


class CashSlice(NamedTuple):
    """One account's cash, CAD-normalized, tagged with its ledger currency."""

    account: str
    currency: str
    value: float


def _classification(
    value: Optional[str], category: Category, security_type: str
) -> str:
    if value:
        return value
    if category == Category.FIXED_INCOME:
        return str(Category.FIXED_INCOME)
    if security_type == SecurityType.ETF:
        return ETF_UNCLASSIFIED_LABEL
    return UNCLASSIFIED_LABEL


def build_allocation_rows(
    holdings: Iterable[Holding],
    securities: Mapping[str, "Security"],
    cash_slices: Iterable[CashSlice],
) -> pd.DataFrame:
    """One row per holding plus one per account with positive cash.

    Negative cash (margin) is a liability, not an allocation, so it is left out.
    """
    rows: list[dict[str, Any]] = []
    for h in holdings:
        security = securities.get(h.symbol)
        profile = security.profile if security else None
        security_type = str(h.security_type)
        rows.append(
            {
                "symbol": h.symbol,
                "name": h.name,
                "value": h.market_value,
                "is_option": h.holding_category in OPTION_CATEGORIES,
                "asset_type": (
                    str(Category.FIXED_INCOME)
                    if h.holding_category == Category.FIXED_INCOME
                    else security_type
                ),
                "instrument": str(h.holding_category),
                "sector": _classification(
                    profile.sector if profile else None,
                    h.holding_category,
                    security_type,
                ),
                "country": _classification(
                    profile.country if profile else None,
                    h.holding_category,
                    security_type,
                ),
                "currency": h.currency,
                "account": h.account or "",
            }
        )
    for cash in cash_slices:
        if cash.value > 0:
            rows.append(
                {
                    "symbol": CASH_LABEL.upper(),
                    "name": CASH_LABEL,
                    "value": cash.value,
                    "is_option": False,
                    "asset_type": CASH_LABEL,
                    "instrument": CASH_LABEL,
                    "sector": CASH_LABEL,
                    "country": CASH_LABEL,
                    "currency": cash.currency,
                    "account": cash.account,
                }
            )
    columns = ["symbol", "name", "value", "is_option", *DIMENSIONS]
    return pd.DataFrame(rows, columns=columns)


def calc_breakdown(rows: pd.DataFrame, dimension: str) -> list[dict[str, Any]]:
    """Value and share of the total per label of `dimension`, largest first."""
    total = float(rows["value"].sum())
    if rows.empty or total <= 0:
        return []
    grouped = rows.groupby(dimension)["value"].sum()
    grouped = grouped[grouped > 0].sort_values(ascending=False)
    return [
        {"label": str(label), "market_value": float(v), "weight": float(v) / total}
        for label, v in grouped.items()
    ]


def calc_symbol_weights(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Per-symbol rollup across accounts; options sit under their underlying."""
    total = float(rows["value"].sum())
    held = rows[rows["instrument"] != CASH_LABEL]
    if held.empty or total <= 0:
        return []
    out = []
    for symbol, group in held.groupby("symbol"):
        value = float(group["value"].sum())
        if value <= 0:
            continue
        options_value = float(group.loc[group["is_option"], "value"].sum())
        out.append(
            {
                "symbol": str(symbol),
                "name": str(group["name"].iloc[0]),
                "market_value": value,
                "weight": value / total,
                "shares_value": value - options_value,
                "options_value": options_value,
            }
        )
    return sorted(out, key=lambda r: r["market_value"], reverse=True)


def calc_concentration(weights: Iterable[float]) -> dict[str, float]:
    """Concentration of the invested (non-cash) part of the portfolio."""
    w = np.sort(np.array([x for x in weights if x > 0], dtype=float))[::-1]
    if w.size == 0:
        return {
            "holdings": 0,
            "top1": 0.0,
            "top5": 0.0,
            "top10": 0.0,
            "hhi": 0.0,
            "effective_n": 0.0,
        }
    w = w / w.sum()
    hhi = float(np.sum(w**2))
    return {
        "holdings": int(w.size),
        "top1": float(w[:1].sum()),
        "top5": float(w[:5].sum()),
        "top10": float(w[:10].sum()),
        "hhi": hhi,
        "effective_n": 1.0 / hhi,
    }


def calc_risk_contribution(
    weights: Mapping[str, float],
    covariance: pd.DataFrame,
    observations: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Each symbol's share of invested value next to its share of volatility.

    Risk share is `w_i · (Σw)_i / w'Σw` over the symbols with enough return
    history; the rest get None rather than a misleading zero. `covariance`
    and `observations` are the portfolio's daily-return statistics.
    """
    invested = sum(v for v in weights.values() if v > 0)
    if invested <= 0:
        return []
    share = {s: v / invested for s, v in weights.items() if v > 0}

    measured = [
        s
        for s in share
        if s in covariance.columns and observations.get(s, 0) >= MIN_RISK_OBS
    ]
    risk: dict[str, float] = {}
    if measured:
        w = np.array([share[s] for s in measured], dtype=float)
        w = w / w.sum()
        cov = covariance.loc[measured, measured].fillna(0.0).to_numpy()
        marginal = cov @ w
        variance = float(w @ marginal)
        if np.isfinite(variance) and variance > 0:
            risk = dict(zip(measured, (w * marginal / variance).tolist()))

    return [
        {"symbol": s, "weight": share[s], "risk_share": risk.get(s)}
        for s in sorted(share, key=lambda s: share[s], reverse=True)
    ]


def calc_account_mix(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Asset-type split inside each account (weights sum to 1 per account)."""
    if rows["account"].nunique() < 2:
        return []
    grouped = rows.groupby(["account", "asset_type"])["value"].sum()
    grouped = grouped[grouped > 0]
    totals = grouped.groupby(level="account").sum()
    return [
        {
            "account": str(account),
            "label": str(label),
            "market_value": float(v),
            "weight": float(v) / float(totals[account]),
        }
        for (account, label), v in grouped.items()
    ]


def compute_allocation(
    holdings: Iterable[Holding],
    securities: Mapping[str, "Security"],
    cash_slices: Iterable[CashSlice],
    covariance: pd.DataFrame,
    observations: Mapping[str, float],
) -> dict[str, Any]:
    """`covariance` / `observations` are the portfolio's return statistics,
    the same ones its correlation matrix is built from."""
    cash_slices = list(cash_slices)
    rows = build_allocation_rows(holdings, securities, cash_slices)
    by_symbol = calc_symbol_weights(rows)
    symbol_values = {r["symbol"]: r["market_value"] for r in by_symbol}

    return {
        "by_symbol": by_symbol,
        "breakdowns": {d: calc_breakdown(rows, d) for d in DIMENSIONS},
        "concentration": calc_concentration(symbol_values.values()),
        "risk_contribution": calc_risk_contribution(
            symbol_values, covariance, observations
        ),
        "account_mix": calc_account_mix(rows),
        "margin": -sum(c.value for c in cash_slices if c.value < 0),
    }
