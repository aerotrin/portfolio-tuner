from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.security import SecurityType

QTY_EFFECT: dict[str, int] = {
    "Buy": +1,
    "Purchase": +1,
    "Split": +1,  # extra shares or reduced shares (-ve) - keeps original sign
    "Disburse": +1,  # extra shares
    "Sell": -1,
    "Sold": -1,
    "Expired": -1,  # option expires worthless
    "Redeemed": -1,  # treat like sell - e.g. applies to units of GIC
    "Exchange": 0,  # ignore - e.g. used for name/symbol changes
    "Contrib": 0,
    "EFT": 0,
    "Transfer": 0,
    "Transf In": 0,
    "Withdrawal": 0,
    "Dividend": 0,
    "Interest": 0,
    "Tax": 0,
    "HST": 0,
    "Fee": 0,
}


class TransactionKind(StrEnum):
    BUY = "Buy"
    PURCHASE = "Purchase"
    SPLIT = "Split"
    DISBURSE = "Disburse"
    SELL = "Sell"
    SOLD = "Sold"
    EXPIRED = "Expired"
    REDEEMED = "Redeemed"
    EXCHANGE = "Exchange"
    CONTRIB = "Contrib"
    EFT = "EFT"
    TRANSFER = "Transfer"
    TRANSF_IN = "Transf In"
    WITHDRAWAL = "Withdrawal"
    DIVIDEND = "Dividend"
    INTEREST = "Interest"
    TAX = "Tax"
    HST = "HST"
    FEE = "Fee"


CASH_TRANSACTIONS = {"Contrib", "Transf In", "EFT", "Transfer", "Withdrawal"}
INCOME_TRANSACTIONS = {"Dividend", "Interest"}
EXPENSE_TRANSACTIONS = {"Tax", "HST", "Fee"}


class Category(StrEnum):
    CASH = "Cash"
    INCOME = "Income"
    EXPENSE = "Expense"
    CALL_OPTION = "Call Option"
    PUT_OPTION = "Put Option"
    FIXED_INCOME = "Fixed Income"
    EQUITY = "Equity"


class Currency(StrEnum):
    CAD = "CAD"
    USD = "USD"


# Input/Output entities
class Transaction(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_date: date = Field(default_factory=date.today)
    settlement_date: date = Field(
        default_factory=lambda: date.today() + timedelta(days=2)
    )
    transaction_type: TransactionKind = TransactionKind.BUY
    symbol: str = ""
    market: str = ""
    description: str = ""
    quantity: int = 0
    currency: Currency = Currency.CAD
    price: float = 0.0
    commission: float = 0.0
    exchange_rate: float = 0.0
    fees_paid: float = 0.0
    amount: float = 0.0


class TransactionCreateDTO(BaseModel):
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


# Output only entities


class AccountSummaryDTO(BaseModel):
    number: str
    name: str | None
    cash_balance: float
    book_value_securities: float
    net_investment: float
    open_positions: list[str]


class OpenLot(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    symbol: str
    option_osi: Optional[str] = None
    category: Category
    open_date: date
    option_expiry: Optional[date] = None
    option_strike: Optional[float] = None
    open_qty: int
    acb_per_sh: float
    book_value: float


class Holding(BaseModel):
    # Contains all Quote fields
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    symbol: str
    name: str
    exchange: Optional[str] = None
    open: float
    high: float
    low: float
    close: float
    currency: str
    volume: float
    change: float
    change_percent: float
    previous_close: float
    timestamp: datetime = Field(default_factory=datetime.now)
    holding_category: Category
    security_type: SecurityType
    fx_rate: float
    open_date: date
    option_osi: Optional[str] = None
    option_strike: Optional[float] = None
    option_expiry: Optional[date] = None
    option_value: Optional[float] = None
    option_change: Optional[float] = None
    option_change_pct: Optional[float] = None
    option_dte: Optional[int] = None
    option_expired: Optional[bool] = None
    open_qty: int
    breakeven_price: float
    book_value: float = 0.0
    market_value: float = 0.0
    gain: float
    gain_pct: float
    weight: float
    intraday_change: float
    intraday_change_pct: float
    distance_to_breakeven: float
    fx_exposure: float
    pnl_contribution: float
    intraday_contribution: float
    days_held: int


class ClosedLot(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    symbol: str
    option_osi: Optional[str] = None
    category: Category
    transaction_type: TransactionKind
    close_date: date
    option_expiry: Optional[date] = None
    description: str
    close_qty: int
    price: float
    currency: Currency
    proceeds: float
    cost_basis: float
    gain: float
    gain_pct: float
    last_open_date: date
    days_held: int
    is_expired: bool


class CashFlow(BaseModel):
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    transaction_date: date
    settlement_date: Optional[date] = None
    category: Category
    transaction_type: TransactionKind
    description: str
    market: str
    quantity: Optional[int] = None
    currency: Currency
    amount: float
