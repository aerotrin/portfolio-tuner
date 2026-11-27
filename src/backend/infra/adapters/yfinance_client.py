"""Yahoo Finance market data adapter (yfinance)."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
import math
from typing import Any, Callable, Optional, TypeVar

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from backend.application.ports.market_data_provider import (
    MarketDataProvider,
    ProviderRateLimitError,
)
from backend.domain.entities.security import (
    Bar,
    GlobalRates,
    Profile,
    Quote,
    SecurityType,
    finite_or_zero,
)
from backend.infra.adapters.rate_limiter import RateLimiter, RateLimiterConfig

logger = logging.getLogger(__name__)

_QUOTE_TYPE_MAP: dict[str, SecurityType] = {
    "EQUITY": SecurityType.STOCK,
    "ETF": SecurityType.ETF,
    "INDEX": SecurityType.INDEX,
    "CRYPTOCURRENCY": SecurityType.CRYPTO,
    "CURRENCY": SecurityType.FOREX,
    "MUTUALFUND": SecurityType.MUTUAL_FUND,
}


T = TypeVar("T")

DEFAULT_MAX_PER_MINUTE = 600
# Upstream requests behind one call, charged to the rate limiter:
# fast_info loads daily and intraday price history; info loads the quote
# summary, the v7 quote and key statistics.
QUOTE_REQUESTS = 2
PROFILE_REQUESTS = 3


def paced_limiter_config(max_per_minute: int) -> RateLimiterConfig:
    """Spread the minute's budget evenly instead of sending it in one burst."""
    return RateLimiterConfig(
        max_per_minute=max_per_minute, min_interval_sec=60.0 / max_per_minute
    )


@dataclass
class YFinanceConfig:
    default_days_back: int = 365
    rate_limiter: RateLimiterConfig = field(
        default_factory=lambda: paced_limiter_config(DEFAULT_MAX_PER_MINUTE)
    )
    max_retries: int = 3
    # Yahoo sends no Retry-After; the limiter multiplies this by 2, 4 and 8
    retry_base_sec: int = 15


def _market_time(value: Any) -> datetime:
    """Last trade time from the history metadata: epoch seconds or a datetime."""
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _first_finite(info: dict, *keys: str) -> Optional[float]:
    for key in keys:
        value = info.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _dividend_rate(info: dict) -> Optional[float]:
    """Annual dividend per share. Funds publish a yield instead of a rate, so
    theirs is recovered from the yield and the price it was quoted at."""
    rate = _first_finite(info, "dividendRate")
    if rate is not None:
        return rate
    fund_yield = _first_finite(info, "yield")
    price = _first_finite(info, "regularMarketPrice", "previousClose")
    if fund_yield is not None and price is not None:
        return fund_yield * price
    return None


class YFinanceClient(MarketDataProvider):
    """
    Thin wrapper around yfinance that satisfies the MarketDataProvider protocol.

    Every Yahoo call goes through `_call`, which paces requests with a
    `RateLimiter`, and on "Too Many Requests" backs off and retries. The
    backoff is shared, so all threads pause while Yahoo is refusing.

    fetch_global_rates uses:
      - ^IRX  (13-week T-bill yield) for the risk-free rate
      - USDCAD=X for the USD/CAD exchange rate
    """

    def __init__(self, config: YFinanceConfig | None = None):
        self.cfg = config or YFinanceConfig()
        self._rate_limiter = RateLimiter(self.cfg.rate_limiter)

    def _call(self, fn: Callable[[], T], *, cost: int = 1) -> T:
        """Run a Yahoo call under the rate limiter, retrying when rate limited.

        `fn` must do all its network access before returning (yfinance loads
        lazily). Raises ProviderRateLimitError once retries are used up.
        """
        attempt = 0
        while True:
            self._rate_limiter.acquire_slot(cost)
            try:
                return fn()
            except YFRateLimitError:
                attempt += 1
                if attempt > self.cfg.max_retries:
                    raise ProviderRateLimitError(
                        f"Yahoo still rate limiting after {self.cfg.max_retries} retries"
                    ) from None
                self._rate_limiter.handle_rate_limit(self.cfg.retry_base_sec, attempt)

    # -------------------------------------------------------------------------
    # Protocol methods
    # -------------------------------------------------------------------------

    def fetch_quote(self, symbol: str) -> Quote:
        def load() -> dict[str, Any]:
            # Name and trade time come from the price-history metadata that
            # fast_info has already loaded; ticker.info would cost three more
            # requests per quote.
            ticker = yf.Ticker(symbol)
            fi = ticker.fast_info
            return {
                "previous_close": fi.regular_market_previous_close,
                "last_price": fi.last_price,
                "open": fi.open,
                "high": fi.day_high,
                "low": fi.day_low,
                "volume": fi.last_volume,
                "exchange": fi.exchange,
                "currency": fi.currency,
                "meta": ticker.get_history_metadata() or {},
            }

        try:
            raw = self._call(load, cost=QUOTE_REQUESTS)
            meta = raw["meta"]

            # fast_info yields None or NaN for fields the market has not
            # published yet (premarket last price, previous close); NaN is
            # truthy, so `or 0.0` alone would let it through.
            previous_close: float = finite_or_zero(raw["previous_close"])
            last_price: float = finite_or_zero(raw["last_price"])
            change = (
                last_price - previous_close if previous_close and last_price else 0.0
            )
            change_pct = (change / previous_close) if previous_close else 0.0
        except Exception as e:
            logger.warning("Quote fetch failed for %s: %s", symbol, e)
            raise

        try:
            return Quote(
                symbol=symbol,
                name=meta.get("longName") or meta.get("shortName") or "",
                exchange=raw["exchange"] or "",
                open=finite_or_zero(raw["open"]),
                high=finite_or_zero(raw["high"]),
                low=finite_or_zero(raw["low"]),
                close=last_price,
                currency=raw["currency"]
                or ("CAD" if symbol.endswith(".TO") else "USD"),
                volume=finite_or_zero(raw["volume"]),
                change=change,
                change_percent=change_pct,
                previousClose=previous_close,
                timestamp=_market_time(meta.get("regularMarketTime")),
            )
        except Exception as e:
            logger.warning("Quote build failed for %s: %s", symbol, e)
            raise

    def fetch_batch_quotes(self, symbols: list[str]) -> list[Quote]:
        quotes: list[Quote] = []
        for symbol in symbols:
            try:
                quotes.append(self.fetch_quote(symbol))
            except Exception:
                logger.warning("Fetch quote failed for symbol %s, skipping", symbol)
        return quotes

    def fetch_bars(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> list[Bar]:
        try:
            start = from_date or date.today() - timedelta(
                days=self.cfg.default_days_back
            )
            end = (
                (to_date + timedelta(days=1)) if to_date else date.today()
            )  # FTRK-498: yFinance end date is exclusive, so add 1 day

            df = self._call(lambda: yf.Ticker(symbol).history(start=start, end=end))

            if df.empty:
                raise RuntimeError(f"No bars data for {symbol}")
        except Exception as e:
            logger.warning("Bars fetch failed for %s: %s", symbol, e)
            raise

        # yfinance returns data oldest-first; convert DatetimeIndex to plain datetime
        try:
            return [
                Bar(
                    symbol=symbol,
                    date=ts.date(),
                    open=row["Open"],
                    high=row["High"],
                    low=row["Low"],
                    close=row["Close"],
                    volume=row["Volume"],
                )
                for ts, row in df.iterrows()
            ]
        except Exception as e:
            logger.warning("Bars build failed for %s: %s", symbol, e)
            raise

    def fetch_global_rates(self) -> GlobalRates:
        try:
            # Risk-free rate: 13-week T-bill (^IRX), yield returned as a percentage
            rf_raw: float | None = self._call(
                lambda: yf.Ticker("^IRX").fast_info.last_price, cost=QUOTE_REQUESTS
            )
            rf_rate = (rf_raw / 100.0) if rf_raw is not None else 0.0

            # FX rate: USD/CAD
            fx_rate: float = (
                self._call(
                    lambda: yf.Ticker("USDCAD=X").fast_info.last_price,
                    cost=QUOTE_REQUESTS,
                )
                or 0.0
            )

            return GlobalRates(
                date=datetime.now(timezone.utc),
                rf_rate=rf_rate,
                fx_rate=fx_rate,
            )
        except Exception as e:
            logger.warning("Global rates fetch failed: %s", e)
            raise

    def fetch_stock_profile(self, symbol: str) -> Profile:
        try:
            info: dict = self._call(
                lambda: yf.Ticker(symbol).info, cost=PROFILE_REQUESTS
            )
        except Exception as e:
            logger.warning("Profile request failed for %s: %s", symbol, e)
            raise

        if (
            not info.get("quoteType")
            and not info.get("longName")
            and not info.get("shortName")
        ):
            raise ValueError(f"No profile data for symbol {symbol}")

        quote_type = info.get("quoteType", "")
        security_type = _QUOTE_TYPE_MAP.get(quote_type, SecurityType.UNKNOWN)

        try:
            return Profile(
                symbol=symbol,
                date=datetime.now(timezone.utc),
                name=info.get("longName") or info.get("shortName"),
                type=security_type,
                exchange=info.get("exchange"),
                currency=info.get("currency"),
                marketCap=info.get("marketCap"),
                beta=info.get("beta"),
                lastDividend=info.get("trailingAnnualDividendRate"),
                averageVolume=info.get("averageVolume"),
                yearHigh=info.get("fiftyTwoWeekHigh"),
                yearLow=info.get("fiftyTwoWeekLow"),
                isin=info.get("isin"),
                cusip=None,  # not exposed by yfinance
                industry=info.get("industry"),
                sector=info.get("sector"),
                country=info.get("country"),
                epsTrailing=_first_finite(
                    info, "trailingEps", "epsTrailingTwelveMonths"
                ),
                epsForward=_first_finite(info, "forwardEps", "epsForward"),
                dividendRate=_dividend_rate(info),
                # Yahoo's share counts for funds do not match their net assets
                sharesOutstanding=(
                    _first_finite(info, "impliedSharesOutstanding", "sharesOutstanding")
                    if quote_type == "EQUITY"
                    else None
                ),
                netAssets=_first_finite(info, "netAssets", "totalAssets"),
            )
        except Exception as e:
            logger.warning("Profile build failed for %s: %s", symbol, e)
            raise
