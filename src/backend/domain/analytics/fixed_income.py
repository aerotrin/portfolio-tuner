from datetime import date, datetime, timedelta
import re
from typing import Iterable, Optional
import uuid

import numpy as np

from backend.domain.entities.fixed_income import (
    Compounding,
    FixedIncomeStatus,
    FixedIncomeType,
    InstrumentTerms,
)

# Shared by fixed-income rows whose description carries no parseable terms
UNKNOWN_TERMS_SYMBOL = "FIXED-INCOME"

_LEDGER_TERMS = re.compile(
    r"Maturity\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\s+Coupon\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_LEDGER_NAME = re.compile(r"^(.*?)\s{2,}")


def _add_years(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:  # Feb 29 into a non-leap year
        return start.replace(year=start.year + years, day=28)


def _whole_years_and_days(start: date, end: date) -> tuple[int, int]:
    if end <= start:
        return 0, 0
    years = end.year - start.year
    if _add_years(start, years) > end:
        years -= 1
    return years, (end - _add_years(start, years)).days


def year_fraction(start: date, end: date) -> float:
    """Whole anniversaries plus the remaining days over 365.

    Counting anniversaries keeps a one-year term at exactly 1.0 across a leap
    day, which is how issuers pay it.
    """
    years, days = _whole_years_and_days(start, end)
    return years + min(days, 365) / 365


def accrual_factor(terms: InstrumentTerms, as_of: date) -> float:
    """Growth of one unit of principal from issue through `as_of`, payouts ignored.

    Interest is earned from the issue date inclusive, so `as_of` itself counts
    as an earned day, which is how issuers report a deposit's current value.
    Flat at 1.0 before issue and at the maturity factor from the day before
    maturity onward.
    """
    earned_to = as_of + timedelta(days=1)
    end = min(max(earned_to, terms.issue_date), terms.maturity_date)
    years, days = _whole_years_and_days(terms.issue_date, end)
    partial = min(days, 365) / 365
    rate = terms.annual_rate
    if terms.compounding == Compounding.ANNUAL:
        return float((1 + rate) ** years * (1 + rate * partial))
    return 1 + rate * (years + partial)


def interest_earned(principal: float, terms: InstrumentTerms, as_of: date) -> float:
    return principal * (accrual_factor(terms, as_of) - 1)


def accrued_interest(
    principal: float,
    terms: InstrumentTerms,
    as_of: date,
    interest_received: float = 0.0,
) -> float:
    """Interest earned to date that has not been paid out yet."""
    return max(interest_earned(principal, terms, as_of) - interest_received, 0.0)


def accrued_value(
    principal: float,
    terms: InstrumentTerms,
    as_of: date,
    interest_received: float = 0.0,
) -> float:
    return principal + accrued_interest(principal, terms, as_of, interest_received)


def maturity_value(principal: float, terms: InstrumentTerms) -> float:
    """Principal plus all interest over the term, payouts ignored."""
    return principal * accrual_factor(terms, terms.maturity_date)


def instrument_status(terms: InstrumentTerms, as_of: date) -> FixedIncomeStatus:
    if as_of >= terms.maturity_date:
        return FixedIncomeStatus.MATURED
    return FixedIncomeStatus.ACTIVE


def days_to_maturity(terms: InstrumentTerms, as_of: date) -> int:
    return (terms.maturity_date - as_of).days


def accrual_index(terms: InstrumentTerms, dates: Iterable[date]) -> np.ndarray:
    """Accrual factor on each of `dates`."""
    return np.array([accrual_factor(terms, d) for d in dates], dtype=float)


def parse_ledger_terms(
    description: str, settlement_date: Optional[date]
) -> Optional[InstrumentTerms]:
    """Terms from a broker description like '... Maturity NOV 07 2024 Coupon 5.00'.

    The ledger carries no issue date, so the row's settlement date stands in.
    """
    match = _LEDGER_TERMS.search(description or "")
    if not match:
        return None
    month, day, year, coupon = match.groups()
    try:
        maturity = datetime.strptime(f"{month.title()} {day} {year}", "%b %d %Y").date()
    except ValueError:
        return None
    issue = settlement_date if settlement_date and settlement_date < maturity else None
    if issue is None:
        # A payout or redemption row settles on or after maturity; only the
        # maturity and coupon matter there, for the instrument key
        issue = _add_years(maturity, -1)
    name_match = _LEDGER_NAME.match(description.strip())
    name = name_match.group(1) if name_match else ""
    try:
        return InstrumentTerms(
            type=FixedIncomeType.GIC,
            name=name.strip(),
            issue_date=issue,
            maturity_date=maturity,
            annual_rate=float(coupon) / 100,
        )
    except ValueError:
        return None


def instrument_key(terms: InstrumentTerms) -> str:
    """Holding key for an instrument, e.g. 'GIC-5.00-20241107'.

    Never a valid ticker, so it can't be mistaken for a market symbol.
    """
    prefix = "GIC" if terms.type == FixedIncomeType.GIC else "TD"
    return f"{prefix}-{terms.annual_rate * 100:.2f}-{terms.maturity_date:%Y%m%d}"


def new_instrument_symbol(terms: InstrumentTerms) -> str:
    """Unique key for a manually entered instrument."""
    return f"{instrument_key(terms)}-{uuid.uuid4().hex[:4]}"


def ledger_description(terms: Optional[InstrumentTerms], note: str = "") -> str:
    """Description in the broker's wording, so the row parses back to its key."""
    if terms is None:
        return f"FIXED INCOME COUPON  {note}".strip().upper()
    base = terms.name or str(terms.type)
    return (
        (
            f"{base}  Maturity {terms.maturity_date:%b %d %Y} "
            f"Coupon {terms.annual_rate * 100:.2f}  {note}"
        )
        .strip()
        .upper()
    )


def instrument_label(terms: InstrumentTerms) -> str:
    """Display name: the issuer name with rate and maturity."""
    base = terms.name or str(terms.type)
    return f"{base} {terms.annual_rate * 100:.2f}% {terms.maturity_date:%b %d %Y}"
