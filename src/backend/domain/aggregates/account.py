from typing import List

import pandas as pd

from backend.domain.analytics.account import run_records_parser
from backend.domain.entities.account import (
    CASH_TRANSACTIONS,
    CashFlow,
    ClosedLot,
    EXPENSE_TRANSACTIONS,
    INCOME_TRANSACTIONS,
    OpenLot,
    Transaction,
)


class Account:
    """An account is a collection of open/closed positions and cash flows."""

    def __init__(
        self,
        account_number: str,
        transactions: List[Transaction],
        account_name: str | None = None,
    ):
        self.number = account_number
        self.name = account_name or account_number
        self.transactions = transactions

        self.open_positions: list[OpenLot] = []
        self.closed_positions: list[ClosedLot] = []
        self.cash_flows: list[CashFlow] = []
        self.external_cash_flows: list[CashFlow] = []
        self.income: list[CashFlow] = []
        self.expenses: list[CashFlow] = []

        # Quick attributes
        self.cash_balance: float = 0.0
        self.book_value_securities: float = 0.0

        if not self.transactions:
            return
        self.build()

    def build(self) -> None:
        """Build positions for this account's transactions."""
        transactions_df = pd.DataFrame([t.model_dump() for t in self.transactions])
        transactions_df = transactions_df.sort_values(
            by="transaction_date", ascending=True
        ).reset_index(drop=True)

        self.cash_balance = transactions_df["amount"].sum()
        self.open_positions, self.closed_positions, self.cash_flows = (
            run_records_parser(transactions_df)
        )

        self.book_value_securities = sum(o.book_value for o in self.open_positions)

        self.external_cash_flows = [
            c for c in self.cash_flows if c.transaction_type in CASH_TRANSACTIONS
        ]
        self.income = [
            c for c in self.cash_flows if c.transaction_type in INCOME_TRANSACTIONS
        ]
        self.expenses = [
            c for c in self.cash_flows if c.transaction_type in EXPENSE_TRANSACTIONS
        ]
