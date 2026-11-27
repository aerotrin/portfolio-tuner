from datetime import date as dt_date, datetime
from enum import StrEnum
import math
from typing import Annotated, Any, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def finite_or_zero(value: Any) -> Any:
    """Coerce missing or non-finite numbers to 0.0.

    Providers hand back None or NaN for fields that are not published yet
    (premarket last price, previous close, day range). NaN survives float
    validation and Postgres storage, but pydantic serializes it as JSON null,
    so it reaches the frontend as None and breaks arithmetic there.
    """
    if value is None:
        return 0.0
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return value


FiniteFloat = Annotated[float, BeforeValidator(finite_or_zero)]


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
    # Slow-moving inputs; price-sensitive ratios are derived from them
    epsTrailing: Optional[float] = Field(default=None)
    epsForward: Optional[float] = Field(default=None)
    dividendRate: Optional[float] = Field(default=None)
    sharesOutstanding: Optional[float] = Field(default=None)
    netAssets: Optional[float] = Field(default=None)


class Fundamentals(BaseModel):
    market_cap: Optional[float] = None
    net_assets: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None


class Quote(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field()
    name: str = Field()
    exchange: str = Field()
    open: FiniteFloat = Field()
    high: FiniteFloat = Field()
    low: FiniteFloat = Field()
    close: FiniteFloat = Field()
    currency: str = Field()
    volume: FiniteFloat = Field()
    change: FiniteFloat = Field()
    change_percent: FiniteFloat = Field()
    previousClose: FiniteFloat = Field()
    timestamp: datetime = Field()


class Bar(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field()
    open: float = Field()
    high: float = Field()
    low: float = Field()
    close: float = Field()
    volume: float = Field()
    date: dt_date = Field()


class BarsSyncState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    last_bar_date: Optional[dt_date] = None
    last_checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    status: str = "pending"


class GlobalRates(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime = Field(default_factory=datetime.now)
    rf_rate: Optional[float] = Field(
        default=0.0,
        description="Annual risk-free rate as a decimal fraction (0.038 = 3.8%)",
    )
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
    max_drawdown_date: Optional[dt_date] = Field(default=None)
    rsi_slope: float = Field(default=0.0)
    near_52wk_hi: bool = Field(default=False)
    near_52wk_lo: bool = Field(default=False)
    avg_volume: Optional[float] = Field(default=None)
    relative_volume: Optional[float] = Field(default=None)
    dollar_volume: Optional[float] = Field(default=None)
    high_52w: Optional[float] = Field(default=None)
    low_52w: Optional[float] = Field(default=None)
    market_cap: Optional[float] = Field(default=None)
    net_assets: Optional[float] = Field(default=None)
    trailing_pe: Optional[float] = Field(default=None)
    forward_pe: Optional[float] = Field(default=None)
    eps: Optional[float] = Field(default=None)
    dividend_yield: Optional[float] = Field(default=None)
    last_calculated: datetime = Field(default_factory=datetime.now)


class MovingAverageSeries(BaseModel):
    kind: str
    period: int
    values: List[Optional[float]]


class PriceChartSeries(BaseModel):
    """Columnar daily series; indicator warm-up rows are null."""

    dates: List[dt_date]
    open: List[Optional[float]]
    high: List[Optional[float]]
    low: List[Optional[float]]
    close: List[Optional[float]]
    volume: List[Optional[float]]
    moving_averages: List[MovingAverageSeries]
    bb_middle: List[Optional[float]]
    bb_upper: List[Optional[float]]
    bb_lower: List[Optional[float]]
    rsi: List[Optional[float]]
    macd: List[Optional[float]]
    macd_signal: List[Optional[float]]
    macd_histogram: List[Optional[float]]


class PriceChartRange(BaseModel):
    key: str
    sessions: int
    change: Optional[float] = None
    change_percent: Optional[float] = None


class PriceChartSummary(BaseModel):
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    last_price: Optional[float] = None
    change_1d: Optional[float] = None
    change_percent_1d: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    volume: Optional[float] = None
    market_cap: Optional[float] = None
    net_assets: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    last_trade: Optional[datetime] = None


class PriceChart(BaseModel):
    summary: PriceChartSummary
    ranges: List[PriceChartRange]
    series: PriceChartSeries


class SecurityAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote: Quote
    profile: Optional[Profile] = None
    bars: List[Bar]
    metrics: PerformanceMetric
    indicators: List[TimeseriesIndicator]
