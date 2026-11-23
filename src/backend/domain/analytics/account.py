from datetime import date, datetime
import logging
import re
from typing import Optional

import numpy as np
import pandas as pd

from backend.domain.analytics.fixed_income import (
    UNKNOWN_TERMS_SYMBOL,
    instrument_key,
    parse_ledger_terms,
)
from backend.domain.entities.account import (
    CASH_TRANSACTIONS,
    CashFlow,
    Category,
    ClosedLot,
    EXPENSE_TRANSACTIONS,
    INCOME_TRANSACTIONS,
    OpenLot,
    QTY_EFFECT,
    ROC_TRANSACTIONS,
)
from backend.domain.entities.fixed_income import InstrumentTerms

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
    fi_terms, fi_keys = _resolve_fixed_income(tx)
    tx["fi_terms"] = pd.Series(fi_terms, index=tx.index, dtype=object)
    tx["fi_key"] = pd.Series(fi_keys, index=tx.index, dtype=object)
    tx["symbol"] = tx.apply(_update_symbols, axis=1)
    tx["category"] = tx.apply(_identify_category, axis=1)
    tx["symbol"] = tx.apply(_fixed_income_symbol, axis=1)
    tx["qty_effect"] = tx["transaction_type"].map(lambda t: QTY_EFFECT[t])
    tx["option_expiry"] = tx.apply(_get_option_expiry, axis=1)
    tx["option_strike"] = tx.apply(_get_option_strike, axis=1)
    tx["option_osi"] = tx.apply(_construct_option_osi, axis=1)
    tx["is_expired"] = tx["description"].str.lower().str.contains("expired")

    # Deterministic FIFO
    tx = tx.sort_values(by="transaction_date", ascending=True).reset_index(drop=True)

    return tx


def _none_if_na(value):
    """Normalize pandas NaN/NaT/None and string 'None' to plain None for JSON-safe serialization."""
    try:
        # pd.isna handles: None, NaN, NaT
        if pd.isna(value):
            return None
        # str(None) yields "None" when keys are built with str(); normalize it
        if value == "None":
            return None
        return value
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


def _resolve_fixed_income(
    tx: pd.DataFrame,
) -> tuple[list[Optional[InstrumentTerms]], list[Optional[str]]]:
    """Terms and holding key per row; None where the row is not an instrument.

    Manually entered instruments carry their terms on the opening row and
    their key in the symbol; ledger rows have neither, so both come from the
    description and the symbol column is ignored.
    """
    explicit: dict[str, InstrumentTerms] = {}
    if "instrument_terms" in tx.columns:
        for sym, raw in zip(tx["symbol"], tx["instrument_terms"]):
            if isinstance(raw, (dict, InstrumentTerms)) and _none_if_na(sym):
                explicit[str(sym)] = InstrumentTerms.model_validate(raw)

    terms: list[Optional[InstrumentTerms]] = []
    keys: list[Optional[str]] = []
    for _, r in tx.iterrows():
        sym = _none_if_na(r["symbol"])
        if sym is not None and str(sym) in explicit:
            terms.append(explicit[str(sym)])
            keys.append(str(sym))
            continue
        settlement = _to_python_date(_none_if_na(r.get("settlement_date")))
        parsed = parse_ledger_terms(
            str(r["description"]), settlement if isinstance(settlement, date) else None
        )
        terms.append(parsed)
        keys.append(instrument_key(parsed) if parsed else None)
    return terms, keys


def _fixed_income_symbol(row: pd.Series) -> str:
    if row["fi_key"]:
        return row["fi_key"]
    if row["category"] == Category.FIXED_INCOME and not row["symbol"]:
        return UNKNOWN_TERMS_SYMBOL
    return row["symbol"]


def _native_amount(row: pd.Series) -> float:
    """Row amount in the instrument's own currency."""
    rate = _none_if_na(row.get("exchange_rate"))
    return float(row["amount"] or 0.0) / (float(rate) if rate else 1.0)


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
    if ttype in ROC_TRANSACTIONS:
        return Category.RETURN_OF_CAPITAL
    if row["fi_key"]:
        return Category.FIXED_INCOME
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
    # Summed over the whole ledger, so it doesn't depend on row order
    interest_received: dict[str, float] = {}

    for _, r in tx.iterrows():
        qty_effect = int(r["qty_effect"] or 0)
        quantity = int(r["quantity"] or 0)
        row_qty = qty_effect * quantity
        sym = r["symbol"]
        cat = r["category"]
        if cat in [
            Category.CASH,
            Category.INCOME,
            Category.EXPENSE,
            Category.RETURN_OF_CAPITAL,
        ]:
            if cat == Category.INCOME and r["fi_key"]:
                interest_received[r["fi_key"]] = interest_received.get(
                    r["fi_key"], 0.0
                ) + _native_amount(r)
            cash_flows.append(
                CashFlow(
                    transaction_date=_to_python_date(r["transaction_date"]),
                    settlement_date=_none_if_na(_to_python_date(r["settlement_date"])),
                    category=r["category"],
                    transaction_type=r["transaction_type"],
                    symbol=_none_if_na(sym) or "",
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
                terms=r["fi_terms"],
                principal=0.0,
            )
        lot = lots[key]

        if row_qty > 0:
            cash_out = -float(r["amount"] or 0.0)
            lot["qty_total"] += row_qty
            lot["acb_total"] += cash_out
            lot["principal"] -= _native_amount(r)
            lot["acb_per_sh"] = (
                lot["acb_total"] / lot["qty_total"] if lot["qty_total"] else np.nan
            )
            if lot["first_date"] is None:
                lot["first_date"] = r["transaction_date"]
            continue

        if lot["qty_total"] <= 0:
            logger.warning("Closing row for %s has no open position; skipped", sym)
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
                days_held=int(days_held) if days_held is not None else 0,
                is_expired=is_expired,
            )
        )

        lot["principal"] -= lot["principal"] * qty_sell / lot["qty_total"]
        lot["qty_total"] -= qty_sell
        lot["acb_total"] -= cost_basis
        if lot["qty_total"] == 0:
            lot["acb_total"] = 0.0
            lot["principal"] = 0.0
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
                    currency=lot["currency"],
                    terms=lot["terms"],
                    principal=(
                        lot["principal"]
                        if lot["category"] == Category.FIXED_INCOME
                        else None
                    ),
                    interest_received=interest_received.get(sym, 0.0),
                )
            )

    return open_lots, closed_lots, cash_flows
