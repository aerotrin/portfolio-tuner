from pydantic import BaseModel
from enum import StrEnum
from datetime import date


class Currency(StrEnum):
    CAD = "CAD"
    USD = "USD"


class TransactionKind(StrEnum):
    BUY = "Buy"
    SELL = "Sell"
    EFT = "EFT"


class AssetCategory(StrEnum):
    CASH = "Cash"
    STOCK = "Stock"
    CALL_OPTION = "Call Option"
    PUT_OPTION = "Put Option"
    EQUITY = "Equity"
    INCOME = "Income"
    EXPENSE = "Expense"
    FIXED_INCOME = "Fixed Income"


class TransactionCreate(BaseModel):
    transaction_date: date
    transaction_type: TransactionKind
    symbol: str
    market: str
    description: str
    quantity: int
    currency: Currency
    price: float
    commission: float
    exchange_rate: float
    fees_paid: float
    amount: float
