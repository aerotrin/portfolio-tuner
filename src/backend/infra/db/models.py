from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    pass


class AccountDB(Base):
    __tablename__ = "accounts"
    id = mapped_column(String(36), primary_key=True)
    number = mapped_column(String, unique=True, nullable=False)
    name = mapped_column(String, nullable=True)
    owner = mapped_column(PG_UUID(as_uuid=False), nullable=False)
    type = mapped_column(String, nullable=False)
    currency = mapped_column(String, nullable=False)
    tax_status = mapped_column(String, nullable=False)
    benchmark = mapped_column(String, nullable=False)
    last_modified = mapped_column(DateTime, nullable=False)


class UserDB(Base):
    __tablename__ = "users"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String)
    email = mapped_column(String)


class QuoteDB(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("symbol", name="uq_quotes_symbol"),)
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
    __table_args__ = (
        Index("ix_bars_symbol", "symbol"),
        Index("ix_bars_symbol_date", "symbol", "date"),
    )
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
    __table_args__ = (UniqueConstraint("symbol", name="uq_profiles_symbol"),)
    id = mapped_column(Integer, primary_key=True)
    symbol = mapped_column(String, nullable=False)
    name = mapped_column(String)
    date = mapped_column(DateTime)
    type = mapped_column(String)
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
    __table_args__ = (Index("ix_transactions_account_number", "account_number"),)
    id = mapped_column(String, primary_key=True)
    account_id = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    account_number = mapped_column(String, nullable=False)
    transaction_date = mapped_column(DateTime, nullable=False)
    settlement_date = mapped_column(DateTime, nullable=True)
    transaction_type = mapped_column(String, nullable=False)
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
