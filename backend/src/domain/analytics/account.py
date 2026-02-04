from datetime import date, datetime
import logging
import re
from typing import Optional

import numpy as np
import pandas as pd

from src.domain.entities.account import (
    CASH_TRANSACTIONS,
    CashFlow,
    Category,
    ClosedLot,
    EXPENSE_TRANSACTIONS,
    INCOME_TRANSACTIONS,
    OpenLot,
    QTY_EFFECT,
)

logger = logging.getLogger(__name__)


def run_records_parser(
    transactions: pd.DataFrame,
) -> tuple[
    list[OpenLot],
    list[ClosedLot],
    list[CashFlow],
]:
    """Check open and closed positions from a transactions DataFrame."""
    tx = _prep_transactions(transactions)
    open_lots, closed_lots, cash_flows = _parse_positions(tx)
    return open_lots, closed_lots, cash_flows


def _prep_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    if transactions is None or transactions.empty:
        return pd.DataFrame()

    tx = transactions.copy()

    # Derived columns
    tx["symbol"] = tx.apply(_update_symbols, axis=1)
    tx["category"] = tx.apply(_identify_category, axis=1)
    tx["qty_effect"] = tx["transaction_type"].map(lambda t: QTY_EFFECT[t])
    tx["option_expiry"] = tx.apply(_get_option_expiry, axis=1)
    tx["option_strike"] = tx.apply(_get_option_strike, axis=1)
    tx["option_osi"] = tx.apply(_construct_option_osi, axis=1)
    tx["is_expired"] = tx["description"].str.lower().str.contains("expired")

    # Deterministic FIFO
    tx = tx.sort_values(by="transaction_date", ascending=True).reset_index(drop=True)

    return tx


def _none_if_na(value):
    """Normalize pandas NaN/NaT/None to plain None for JSON-safe serialization."""
    try:
        # pd.isna handles: None, NaN, NaT
        return None if pd.isna(value) else value
    except Exception:
        logger.error(f"Error in _none_if_na: {value}", exc_info=True)
        return value


def _to_python_date(value):
    """Convert pandas Timestamp to Python date for consistent serialization."""
    if isinstance(value, pd.Timestamp):
        try:
            return value.to_pydatetime().date()
        except Exception:
            logger.error(f"Error in _to_python_date: {value}", exc_info=True)
            return value
    return value


def _update_symbols(row: pd.Series) -> str:
    sym = str(row["symbol"])
    mkt = str(row["market"])
    # Rule 1: If symbol has a dot, convert to dash
    if "." in sym:
        sym = sym.replace(".", "-")
    # Rule 2: If market is "CDN"
    if mkt == "CDN" and sym != "" and not sym.endswith(".TO"):
        sym = f"{sym}.TO"
    return sym


def _identify_category(row: pd.Series) -> Category:
    ttype = row["transaction_type"]
    desc = str(row["description"]).strip().lower()
    if ttype in CASH_TRANSACTIONS:
        return Category.CASH
    if ttype in INCOME_TRANSACTIONS:
        return Category.INCOME
    if ttype in EXPENSE_TRANSACTIONS:
        return Category.EXPENSE
    if desc.startswith("call "):
        return Category.CALL_OPTION
    if desc.startswith("put "):
        return Category.PUT_OPTION
    if "coupon" in desc:
        return Category.FIXED_INCOME
    return Category.EQUITY


def _get_option_expiry(row: pd.Series) -> Optional[date]:
    cat = row["category"]
    if cat in [Category.CALL_OPTION, Category.PUT_OPTION]:
        desc = str(row["description"]).strip()
        try:
            m = re.search(r"(\d{2}/\d{2}/\d{2})", desc)
            if m:
                return datetime.strptime(m.group(1), "%m/%d/%y").date()
        except Exception:
            logger.error(f"Error in _get_option_expiry: {row}", exc_info=True)
            return None
    return None


def _get_option_strike(row: pd.Series) -> Optional[float]:
    cat = row["category"]
    if cat in [Category.CALL_OPTION, Category.PUT_OPTION]:
        desc = str(row["description"]).strip()
        try:
            m = re.search(r"\d{2}/\d{2}/\d{2}\s+(\d+(?:\.\d+)?)", desc)
            if m:
                return float(m.group(1))
        except Exception:
            logger.error(f"Error in _get_option_strike: {row}", exc_info=True)
            return None
    return None


def _construct_option_osi(row: pd.Series) -> Optional[str]:
    date_val = row["option_expiry"]
    strike_val = row["option_strike"]
    sym_val = row["symbol"]
    cat = row["category"]

    if date_val is None or strike_val is None or sym_val is None:
        return None
    if cat not in [Category.CALL_OPTION, Category.PUT_OPTION]:
        return None

    try:
        date_str = datetime.strftime(date_val, "%y%m%d")
    except Exception:
        logger.error(f"Error in _construct_option_osi: {row}", exc_info=True)
        return None
    opt_type = "C" if cat == Category.CALL_OPTION else "P"

    try:
        strike_num = float(strike_val)
    except Exception:
        logger.error(f"Error in _construct_option_osi: {row}", exc_info=True)
        return None
    whole = int(strike_num)
    milli = int((strike_num - whole) * 1000)  # truncate
    return f"{sym_val}{date_str}{opt_type}{whole:05d}{milli:03d}"


def _parse_positions(
    tx: pd.DataFrame,
) -> tuple[list[OpenLot], list[ClosedLot], list[CashFlow]]:
    """Single pass engine to extract open and closed positions from a transactions DataFrame."""
    if tx is None or tx.empty:
        return [], [], []

    lots: dict[tuple[str, str], dict] = {}
    open_lots: list[OpenLot] = []
    closed_lots: list[ClosedLot] = []
    cash_flows: list[CashFlow] = []

    for _, r in tx.iterrows():
        qty_effect = int(r["qty_effect"] or 0)
        quantity = int(r["quantity"] or 0)
        row_qty = qty_effect * quantity
        sym = r["symbol"]
        cat = r["category"]
        if cat in [Category.CASH, Category.INCOME, Category.EXPENSE]:
            cash_flows.append(
                CashFlow(
                    transaction_date=_to_python_date(r["transaction_date"]),
                    settlement_date=_none_if_na(_to_python_date(r["settlement_date"])),
                    category=r["category"],
                    transaction_type=r["transaction_type"],
                    description=r["description"],
                    market=r["market"],
                    quantity=_none_if_na(quantity),
                    currency=r["currency"],
                    amount=r["amount"],
                )
            )
            continue

        if row_qty == 0 or sym is None:
            continue

        key = (str(sym), str(r["option_osi"]))
        if key not in lots:
            lots[key] = dict(
                qty_total=0.0,
                acb_total=0.0,
                acb_per_sh=np.nan,
                first_date=None,
                category=r["category"],
                currency=r["currency"],
                option_expiry=r["option_expiry"],
                option_strike=r["option_strike"],
            )
        lot = lots[key]

        if row_qty > 0:
            cash_out = -float(r["amount"] or 0.0)
            lot["qty_total"] += row_qty
            lot["acb_total"] += cash_out
            lot["acb_per_sh"] = (
                lot["acb_total"] / lot["qty_total"] if lot["qty_total"] else np.nan
            )
            if lot["first_date"] is None:
                lot["first_date"] = r["transaction_date"]
            continue

        qty_sell = -row_qty
        if qty_sell > lot["qty_total"]:
            qty_sell = lot["qty_total"]
        cost_basis = (
            qty_sell * lot["acb_per_sh"] if not pd.isna(lot["acb_per_sh"]) else 0.0
        )
        proceeds = float(r["amount"] or 0.0)

        close_tx_date = r.get("transaction_date")
        close_settle_date = r.get("settlement_date")
        close_exp_date = _none_if_na(_to_python_date(r["option_expiry"]))
        is_expired = bool(r["is_expired"])
        if is_expired:
            close_date = close_exp_date
        else:
            close_date = close_settle_date

        first_dt = lot["first_date"]
        days_held = (
            (close_tx_date - first_dt).days if (close_tx_date and first_dt) else None
        )

        closed_lots.append(
            ClosedLot(
                symbol=sym,
                option_osi=_none_if_na(r["option_osi"]),
                category=r["category"],
                transaction_type=r["transaction_type"],
                close_date=_to_python_date(close_date),
                option_expiry=close_exp_date,
                description=r["description"],
                close_qty=qty_sell,
                price=r["price"],
                currency=r["currency"],
                proceeds=proceeds,
                cost_basis=cost_basis,
                gain=proceeds - cost_basis,
                gain_pct=(proceeds - cost_basis) / cost_basis if cost_basis else 0.0,
                last_open_date=_to_python_date(first_dt),
                days_held=int(days_held) if days_held else None,
                is_expired=is_expired,
            )
        )

        lot["qty_total"] -= qty_sell
        lot["acb_total"] -= cost_basis
        if lot["qty_total"] == 0:
            lot["acb_total"] = 0.0
            lot["acb_per_sh"] = np.nan
            lot["first_date"] = None

    for (sym, osi), lot in lots.items():
        if lot["qty_total"] > 0:
            open_lots.append(
                OpenLot(
                    symbol=sym,
                    option_osi=_none_if_na(osi),
                    category=lot["category"],
                    open_date=_to_python_date(lot["first_date"]),
                    option_expiry=_none_if_na(_to_python_date(lot["option_expiry"])),
                    option_strike=_none_if_na(lot["option_strike"]),
                    open_qty=lot["qty_total"],
                    acb_per_sh=lot["acb_per_sh"],
                    book_value=lot["acb_total"],
                )
            )

    return open_lots, closed_lots, cash_flows
