from sqlalchemy import DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, mapped_column

from src.domain.entities.account import TransactionKind
from src.domain.entities.security import SecurityType


class Base(DeclarativeBase):
    pass


class UserDB(Base):
    __tablename__ = "users"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String)
    email = mapped_column(String)


class QuoteDB(Base):
    __tablename__ = "quotes"
    id = mapped_column(Integer, primary_key=True)
    symbol = mapped_column(String, nullable=False)
    name = mapped_column(String)
    exchange = mapped_column(String)
    open = mapped_column(Float)
    high = mapped_column(Float)
    low = mapped_column(Float)
    close = mapped_column(Float)
    currency = mapped_column(String)
    volume = mapped_column(Float)
    change = mapped_column(Float)
    change_percent = mapped_column(Float)
    previousClose = mapped_column(Float)
    timestamp = mapped_column(DateTime)


class BarDB(Base):
    __tablename__ = "bars"
    id = mapped_column(Integer, primary_key=True)
    symbol = mapped_column(String, nullable=False)
    date = mapped_column(DateTime)
    open = mapped_column(Float)
    high = mapped_column(Float)
    low = mapped_column(Float)
    close = mapped_column(Float)
    volume = mapped_column(Float)


class GlobalRatesDB(Base):
    __tablename__ = "global_rates"
    id = mapped_column(Integer, primary_key=True)
    date = mapped_column(DateTime)
    rf_rate = mapped_column(Float)
    fx_rate = mapped_column(Float)


class ProfileDB(Base):
    __tablename__ = "profiles"
    id = mapped_column(Integer, primary_key=True)
    symbol = mapped_column(String, nullable=False)
    name = mapped_column(String)
    date = mapped_column(DateTime)
    type = mapped_column(Enum(SecurityType))
    exchange = mapped_column(String)
    currency = mapped_column(String)
    marketCap = mapped_column(Float)
    beta = mapped_column(Float)
    lastDividend = mapped_column(Float)
    averageVolume = mapped_column(Float)
    yearHigh = mapped_column(Float)
    yearLow = mapped_column(Float)
    isin = mapped_column(String)
    cusip = mapped_column(String)
    industry = mapped_column(String)
    sector = mapped_column(String)
    country = mapped_column(String)


class TransactionDB(Base):
    __tablename__ = "transactions"
    id = mapped_column(String, primary_key=True)
    account_number = mapped_column(String, nullable=False)
    transaction_date = mapped_column(DateTime, nullable=False)
    settlement_date = mapped_column(DateTime, nullable=True)
    transaction_type = mapped_column(Enum(TransactionKind), nullable=False)
    symbol = mapped_column(String, nullable=True)
    market = mapped_column(String, nullable=True)
    description = mapped_column(String, nullable=False)
    quantity = mapped_column(Integer, nullable=True)
    currency = mapped_column(String, nullable=True)
    price = mapped_column(Float, nullable=True)
    commission = mapped_column(Float, nullable=True)
    exchange_rate = mapped_column(Float, nullable=True)
    fees_paid = mapped_column(Float, nullable=False)
    amount = mapped_column(Float, nullable=False)
