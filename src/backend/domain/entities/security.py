from datetime import date, datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SecurityType(StrEnum):
    INDEX = "Index"
    COMMODITY = "Commodity"
    CRYPTO = "Crypto"
    FOREX = "Forex"
    STOCK = "Stock"
    ETF = "ETF"
    BOND = "Bond"
    GIC = "GIC"
    MUTUAL_FUND = "Mutual Fund"
    REAL_ESTATE = "Real Estate"
    REIT = "REIT"
    CASH = "Cash"
    OTHER = "Other"
    UNKNOWN = "Unknown"


# Read/Write from/to ORM models - use from_attributes=True


class Profile(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # FTRK-404

    symbol: str = Field(default="")
    name: Optional[str] = Field(default=None)
    date: datetime = Field()
    type: SecurityType = Field(default=SecurityType.UNKNOWN)
    exchange: Optional[str] = Field(default=None)
    currency: Optional[str] = Field(default=None)
    marketCap: Optional[float] = Field(default=None)
    beta: Optional[float] = Field(default=None)
    lastDividend: Optional[float] = Field(default=None)
    averageVolume: Optional[float] = Field(default=None)
    yearHigh: Optional[float] = Field(default=None)
    yearLow: Optional[float] = Field(default=None)
    isin: Optional[str] = Field(default=None)
    cusip: Optional[str] = Field(default=None)
    industry: Optional[str] = Field(default=None)
    sector: Optional[str] = Field(default=None)
    country: Optional[str] = Field(default=None)


class Quote(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field()
    name: str = Field()
    exchange: str = Field()
    open: float = Field()
    high: float = Field()
    low: float = Field()
    close: float = Field()
    currency: str = Field()
    volume: float = Field()
    change: float = Field()
    change_percent: float = Field()
    previousClose: float = Field()
    timestamp: datetime = Field()


class Bar(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field()
    date: datetime = Field()
    open: float = Field()
    high: float = Field()
    low: float = Field()
    close: float = Field()
    volume: float = Field()


class GlobalRates(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime = Field(default_factory=datetime.now)
    rf_rate: Optional[float] = Field(default=0.0)
    fx_rate: Optional[float] = Field(default=0.0)


class TimeseriesIndicator(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field()
    date: datetime = Field()
    close: float = Field()
    close_norm: float = Field()
    daily_return: float = Field()
    ema12: float = Field()
    ema26: float = Field()
    ema100: float = Field()
    macd_12_26: float = Field()
    macd_signal_9: float = Field()
    macd_histogram: float = Field()
    rsi: float = Field()
    rsi_signal_5: float = Field()


class PerformanceMetric(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field()
    name: str = Field()
    exchange: str = Field()
    currency: str = Field()
    return5D: float = Field(default=0.0)
    return1M: float = Field(default=0.0)
    return3M: float = Field(default=0.0)
    return6M: float = Field(default=0.0)
    return1Y: float = Field(default=0.0)
    volatility: float = Field(default=0.0)
    sharpe: float = Field(default=0.0)
    sortino: float = Field(default=0.0)
    max_drawdown: float = Field(default=0.0)
    max_drawdown_date: Optional[date] = Field(default=None)
    rsi_slope: float = Field(default=0.0)
    near_52wk_hi: bool = Field(default=False)
    near_52wk_lo: bool = Field(default=False)
    last_calculated: datetime = Field(default_factory=datetime.now)
