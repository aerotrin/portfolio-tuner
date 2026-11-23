from datetime import date

import pandas as pd
import pytest

from src.backend.domain.aggregates.account import Account
from src.backend.domain.entities.account import TransactionKind
from src.backend.infra.adapters.excel_pandas_client import _df_to_transactions

GIC_BUY = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon         5.00  FLEXIBLE GIC               AM NON-TRANSFERABLE DUE "
    "11/07/2024 05.000% SECURITIES OF A RELATED ISSUER UNSOLICITED"
)
GIC_INTEREST = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon 5.0000  Maturity NOV 07 2024 Coupon 5.0000 FLEXIBLE GIC               "
    "AM DUE 11/07/2024  INT  5.000% CPN INT   ON   20000 BND REC 11/06/24 PAY "
    "11/07/24"
)
GIC_REDEEMED = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon 5.0000  FLEXIBLE GIC               AM DUE 11/07/2024  INT  5.000% "
    "ISSUE REDEEMED FOR CASH"
)


def _ledger_row(**overrides) -> dict:
    """A row as the bank exports it: long-form dates with a leading space, and
    no Symbol, Market or Currency of Price on fixed-income rows."""
    row = {
        "Transaction Date": " November 7, 2024",
        "Settlement Date": " November 7, 2024",
        "Currency of Sub-account Held In": "CAD",
        "Transaction Type": "Buy",
        "Symbol": None,
        "Market": None,
        "Description": "",
        "Quantity": 0,
        "Currency of Price": None,
        "Price": 0,
        "Commission": None,
        "Exchange Rate": None,
        "Currency of Amount": "CAD",
        "Amount": 0,
    }
    row.update(overrides)
    return row


def _gic_ledger() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _ledger_row(
                **{
                    "Transaction Type": "Redeemed",
                    "Description": GIC_REDEEMED,
                    "Quantity": 20000,
                    "Amount": 20000,
                }
            ),
            _ledger_row(
                **{
                    "Transaction Type": "Interest",
                    "Description": GIC_INTEREST,
                    "Amount": 1000,
                }
            ),
            _ledger_row(
                **{
                    "Transaction Date": " November 6, 2023",
                    "Settlement Date": " November 7, 2023",
                    "Description": GIC_BUY,
                    "Quantity": 20000,
                    "Price": 100,
                    "Amount": -20000,
                }
            ),
        ]
    )


def test_raw_bank_gic_rows_import_with_blank_symbol_and_long_form_dates():
    redeemed, interest, buy = _df_to_transactions(_gic_ledger())

    assert buy.transaction_type == TransactionKind.BUY
    assert buy.transaction_date == date(2023, 11, 6)
    assert buy.settlement_date == date(2023, 11, 7)
    assert buy.symbol == ""
    assert buy.currency == "CAD"
    assert buy.quantity == 20000
    assert buy.amount == pytest.approx(-20000.0)
    assert buy.exchange_rate == 1.0
    assert interest.transaction_type == TransactionKind.INTEREST
    assert redeemed.transaction_type == TransactionKind.REDEEMED


def test_imported_gic_rows_replay_to_one_keyed_instrument():
    transactions = _df_to_transactions(_gic_ledger())

    open_gic = Account("RRSP-1", [transactions[2]])
    (lot,) = open_gic.open_positions
    assert lot.symbol == "GIC-5.00-20241107"
    assert lot.terms.issue_date == date(2023, 11, 7)

    closed_gic = Account("RRSP-1", transactions)
    assert closed_gic.open_positions == []
    assert closed_gic.cash_balance == pytest.approx(1000.0)
    assert closed_gic.income[0].symbol == "GIC-5.00-20241107"


def test_unknown_transaction_type_fails_the_import():
    df = pd.DataFrame([_ledger_row(**{"Transaction Type": "Maturity"})])

    with pytest.raises(ValueError):
        _df_to_transactions(df)
