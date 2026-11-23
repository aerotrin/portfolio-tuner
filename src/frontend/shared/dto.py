from datetime import date, datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

ACCOUNT_NUMBER_PATTERN = r"^[A-Za-z0-9_-]+$"


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


class FixedIncomeType(StrEnum):
    GIC = "GIC"
    TERM_DEPOSIT = "Term Deposit"


class PaymentFrequency(StrEnum):
    AT_MATURITY = "At Maturity"
    ANNUAL = "Annual"
    SEMI_ANNUAL = "Semi-Annual"
    QUARTERLY = "Quarterly"
    MONTHLY = "Monthly"


class Compounding(StrEnum):
    SIMPLE = "Simple"
    ANNUAL = "Annual"


class InstrumentTerms(BaseModel):
    """Terms of a GIC or term deposit; `annual_rate` is a decimal."""

    type: FixedIncomeType = FixedIncomeType.GIC
    name: str = ""
    issue_date: date
    maturity_date: date
    annual_rate: float
    payment_frequency: PaymentFrequency = PaymentFrequency.AT_MATURITY
    compounding: Compounding = Compounding.SIMPLE
    redeemable: bool = False


class FixedIncomeCreate(BaseModel):
    terms: InstrumentTerms
    principal: float
    currency: Currency = Currency.CAD
    fx_rate: float = 1.0
    funded_by_deposit: bool = False


class FixedIncomeRedemption(BaseModel):
    symbol: str
    transaction_date: date
    principal: float
    interest: float = 0.0
    fx_rate: float = 1.0


class FixedIncomeInterest(BaseModel):
    symbol: str
    transaction_date: date
    amount: float
    fx_rate: float = 1.0


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
    number: str = Field(pattern=ACCOUNT_NUMBER_PATTERN)
    name: str
    type: str
    currency: Currency
    tax_status: TaxStatus
    benchmark: str


class AccountPatchRequest(BaseModel):
    number: Optional[str] = Field(default=None, pattern=ACCOUNT_NUMBER_PATTERN)
    name: Optional[str] = None
    type: Optional[str] = None
    currency: Optional[Currency] = None
    tax_status: Optional[TaxStatus] = None
    benchmark: Optional[str] = None
