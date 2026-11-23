import calendar
from collections import Counter
from datetime import date, timedelta
from typing import Any, Mapping

from frontend.shared.accounts import FIXED_INCOME

CUSTOM_TERM = "Custom"

# Label -> (unit, count); maturity is the issue date plus the term
TERM_PRESETS: dict[str, tuple[str, int]] = {
    "30 days": ("days", 30),
    "60 days": ("days", 60),
    "90 days": ("days", 90),
    "180 days": ("days", 180),
    "270 days": ("days", 270),
    "1 year": ("years", 1),
    "18 months": ("months", 18),
    "2 years": ("years", 2),
    "3 years": ("years", 3),
    "4 years": ("years", 4),
    "5 years": ("years", 5),
}
DEFAULT_TERM = "1 year"


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    # Clamp to the month's last day (Jan 31 + 1 month, Feb 29 + 1 year)
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def maturity_for_term(issue: date, term: str) -> date | None:
    """Maturity date for a preset term; None for a custom term."""
    preset = TERM_PRESETS.get(term)
    if preset is None:
        return None
    unit, count = preset
    if unit == "days":
        return issue + timedelta(days=count)
    return _add_months(issue, count * 12 if unit == "years" else count)


def manageable_holdings(
    holdings: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Open fixed-income holdings with known terms, soonest maturity first
    (so matured ones lead), and the number left out for having no terms."""
    fixed = [
        {**holding, "symbol": holding.get("symbol") or key}
        for key, holding in holdings.items()
        if holding.get("holding_category") == FIXED_INCOME
    ]
    known = [h for h in fixed if h.get("fi_principal") is not None]
    known.sort(
        key=lambda h: (
            h.get("fi_days_to_maturity") is None,
            h.get("fi_days_to_maturity") or 0,
        )
    )
    return known, len(fixed) - len(known)


def holding_labels(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Holding key -> name; a name shared by several holdings gets its key."""
    counts = Counter(str(row["name"]) for row in rows)
    return {
        row["symbol"]: (
            str(row["name"])
            if counts[str(row["name"])] == 1
            else f"{row['name']} · {row['symbol']}"
        )
        for row in rows
    }
