from typing import Iterable, Optional

from pydantic import BaseModel

from backend.domain.analytics.allocation import (
    CASH_LABEL,
    OPTION_CATEGORIES,
    CashSlice,
)
from backend.domain.entities.account import AccountEntity, Category, Holding


class SummaryRow(BaseModel):
    """One exported constituent; the same fields for every asset type.

    Values are in CAD, `currency` is the constituent's own currency, and
    `weight` is relative to the snapshot's total value including cash.
    """

    account_number: str
    account_name: str
    account_type: str
    asset_type: str
    symbol: str
    name: str
    currency: str
    quantity: Optional[float] = None
    book_value: float
    market_value: float
    gain: float
    gain_pct: Optional[float] = None
    weight: float


def _asset_type(holding: Holding) -> str:
    if holding.holding_category in OPTION_CATEGORIES:
        return str(holding.holding_category)
    if holding.holding_category == Category.FIXED_INCOME:
        return str(holding.fi_type or holding.security_type)
    return str(holding.security_type)


def _option_label(holding: Holding) -> str:
    right = "Call" if holding.holding_category == Category.CALL_OPTION else "Put"
    parts = [holding.symbol]
    if holding.option_expiry:
        parts.append(holding.option_expiry.strftime("%b %d %Y"))
    if holding.option_strike is not None:
        parts.append(f"{holding.option_strike:g}")
    parts.append(right)
    return " ".join(parts)


def build_summary_rows(
    holdings: Iterable[Holding],
    accounts: Iterable[AccountEntity],
    cash_slices: Iterable[CashSlice],
    total_value: float,
) -> list[SummaryRow]:
    """Flat constituent rows: one per holding plus one cash row per account.

    Sorted by account number, securities by symbol, cash last.
    """
    by_number = {a.number: a for a in accounts}

    def _name_and_type(number: str) -> tuple[str, str]:
        entity = by_number.get(number)
        return (entity.name, entity.type) if entity else ("", "")

    keyed: list[tuple[tuple[str, int, str], SummaryRow]] = []
    for h in holdings:
        is_option = h.holding_category in OPTION_CATEGORIES
        symbol = (h.option_osi or h.symbol) if is_option else h.symbol
        number = h.account or ""
        account_name, account_type = _name_and_type(number)
        row = SummaryRow(
            account_number=number,
            account_name=account_name,
            account_type=account_type,
            asset_type=_asset_type(h),
            symbol=symbol,
            name=_option_label(h) if is_option else h.name,
            currency=str(h.currency),
            quantity=h.open_qty,
            book_value=h.book_value,
            market_value=h.market_value,
            gain=h.gain,
            gain_pct=h.gain_pct,
            weight=h.weight,
        )
        keyed.append(((row.account_number, 0, symbol), row))

    for cash in cash_slices:
        account_name, account_type = _name_and_type(cash.account)
        row = SummaryRow(
            account_number=cash.account,
            account_name=account_name,
            account_type=account_type,
            asset_type=CASH_LABEL,
            symbol=CASH_LABEL.upper(),
            name=f"{CASH_LABEL} ({cash.currency})",
            currency=str(cash.currency),
            book_value=cash.value,
            market_value=cash.value,
            gain=0.0,
            weight=cash.value / total_value if total_value else 0.0,
        )
        keyed.append(((row.account_number, 1, row.symbol), row))

    return [row for _key, row in sorted(keyed, key=lambda item: item[0])]
