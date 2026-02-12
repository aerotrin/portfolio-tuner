import io
import logging
from typing import Dict, List

import pandas as pd

from backend.application.ports.account_data_importer import AccountDataImporter
from backend.domain.entities.account import Transaction, TransactionKind

TT_MAP: Dict[str, TransactionKind] = {e.value: e for e in TransactionKind}

logger = logging.getLogger(__name__)

COL_MAP = {
    "Transaction Date": "transaction_date",
    "Settlement Date": "settlement_date",
    "Transaction Type": "transaction_type",
    "Symbol": "symbol",
    "Market": "market",
    "Description": "description",
    "Quantity": "quantity",
    "Currency of Price": "currency",
    "Price": "price",
    "Commission": "commission",
    "Exchange Rate": "exchange_rate",
    "Amount": "amount",
}
DATE_COLS = ["Transaction Date", "Settlement Date"]
RATE_COLS = ["Exchange Rate"]
NUMERIC_COLS = ["Price", "Quantity", "Commission", "Amount"]


def _df_to_transactions(df: pd.DataFrame) -> List[Transaction]:
    """Parse a raw Excel-derived DataFrame into Transaction entities."""
    df = df[[col for col in df.columns if col in COL_MAP.keys()]].copy()

    try:
        for col in DATE_COLS:
            df[col] = pd.to_datetime(df[col].astype(str).str.strip(), errors="coerce")

        df["Transaction Type"] = (
            df["Transaction Type"].astype(str).str.strip().map(TT_MAP)
        )

        for col in ["Symbol", "Market", "Description"]:
            df[col] = df[col].fillna("").astype(str).str.strip()

        df["Currency of Price"] = (
            df["Currency of Price"].fillna("CAD").astype(str).str.strip()
        )
        for col in RATE_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(1.0)

        for col in NUMERIC_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        transactions: List[Transaction] = []
        for _, row in df.iterrows():
            t = Transaction(
                transaction_date=row["Transaction Date"],
                settlement_date=(
                    row["Settlement Date"]
                    if pd.notna(row["Settlement Date"])
                    else (row["Transaction Date"] + pd.Timedelta(days=2))
                ),
                transaction_type=row["Transaction Type"],
                symbol=str(row["Symbol"]),
                market=str(row["Market"]),
                description=str(row["Description"]),
                quantity=int(row["Quantity"]),
                currency=str(row["Currency of Price"]),
                price=float(row["Price"]),
                commission=float(row["Commission"]),
                exchange_rate=float(row["Exchange Rate"]),
                fees_paid=float(row["Commission"] * row["Exchange Rate"]),
                amount=float(row["Amount"]),
            )
            transactions.append(t)
        return transactions
    except Exception as e:
        logger.error(f"Error parsing Excel file: {e}")
        raise ValueError(f"Error parsing Excel file: {e}")


class ExcelPandasClient(AccountDataImporter):
    def __init__(self):
        pass

    def import_account(
        self, account_number: str, file_content: bytes
    ) -> List[Transaction]:
        try:
            df = pd.read_excel(
                io.BytesIO(file_content),
                sheet_name=account_number,
                engine="openpyxl",
            )
        except ValueError:
            raise ValueError(f"Sheet '{account_number}' not found in Excel file.")
        try:
            transactions = _df_to_transactions(df)
        except Exception:
            raise ValueError("Error parsing Excel file: Invalid data format")
        return transactions
