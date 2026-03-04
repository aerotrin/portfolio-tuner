"""Yahoo Finance market data adapter (yfinance)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Optional

import yfinance as yf

from backend.application.ports.market_data_provider import MarketDataProvider
from backend.domain.entities.security import (
    Bar,
    GlobalRates,
    Profile,
    Quote,
    SecurityType,
)


logger = logging.getLogger(__name__)

_QUOTE_TYPE_MAP: dict[str, SecurityType] = {
    "EQUITY": SecurityType.STOCK,
    "ETF": SecurityType.ETF,
    "INDEX": SecurityType.INDEX,
    "CRYPTOCURRENCY": SecurityType.CRYPTO,
    "CURRENCY": SecurityType.FOREX,
    "MUTUALFUND": SecurityType.MUTUAL_FUND,
}


@dataclass
class YFinanceConfig:
    default_days_back: int = 365


class YFinanceClient(MarketDataProvider):
    """
    Thin wrapper around yfinance that satisfies the MarketDataProvider protocol.

    fetch_global_rates uses:
      - ^IRX  (13-week T-bill yield) for the risk-free rate
      - USDCAD=X for the USD/CAD exchange rate
    """

    def __init__(self, config: YFinanceConfig | None = None):
        self.cfg = config or YFinanceConfig()

    # -------------------------------------------------------------------------
    # Protocol methods
    # -------------------------------------------------------------------------

    def fetch_quote(self, symbol: str) -> Quote:
        try:
            ticker = yf.Ticker(symbol)
            fi = ticker.fast_info
            info = ticker.info

            previous_close: float = fi.previous_close or 0.0
            last_price: float = fi.last_price or 0.0
            change = last_price - previous_close
            change_pct = (change / previous_close) if previous_close else 0.0
        except Exception as e:
            logger.warning("Quote fetch failed for %s: %s", symbol, e)
            raise

        try:
            return Quote(
                symbol=symbol,
                name=info.get("longName") or info.get("shortName") or "",
                exchange=fi.exchange or "",
                open=fi.open or 0.0,
                high=fi.day_high or 0.0,
                low=fi.day_low or 0.0,
                close=last_price,
                currency=fi.currency or ("CAD" if symbol.endswith(".TO") else "USD"),
                volume=fi.last_volume or 0.0,
                change=change,
                change_percent=change_pct,
                previousClose=previous_close,
                timestamp=datetime.fromtimestamp(
                    info["regularMarketTime"], tz=timezone.utc
                )
                if info.get("regularMarketTime")
                else datetime.now(timezone.utc),
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

            df = yf.Ticker(symbol).history(start=start, end=end)

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
            rf_raw: float | None = yf.Ticker("^IRX").fast_info.last_price
            rf_rate = (rf_raw / 100.0) if rf_raw is not None else 0.0

            # FX rate: USD/CAD
            fx_rate: float = yf.Ticker("USDCAD=X").fast_info.last_price or 0.0

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
            info: dict = yf.Ticker(symbol).info
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
            )
        except Exception as e:
            logger.warning("Profile build failed for %s: %s", symbol, e)
            raise
