from pydantic import BaseModel, ConfigDict
from enum import StrEnum
from datetime import date, datetime
from typing import Optional


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


class TaxStatus(StrEnum):
    REGISTERED = "Registered"
    NON_REGISTERED = "Non-Registered"


class AccountEntity(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    number: str
    name: str = ""
    owner: str
    type: str
    currency: Currency
    tax_status: TaxStatus
    benchmark: str
    last_modified: datetime


class AccountCreateRequest(BaseModel):
    number: str
    name: str
    type: str
    currency: Currency
    tax_status: TaxStatus
    benchmark: str


class AccountPatchRequest(BaseModel):
    number: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    currency: Optional[Currency] = None
    tax_status: Optional[TaxStatus] = None
    benchmark: Optional[str] = None
