"""https://site.financialmodelingprep.com/developer/docs"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
import re
from typing import Any

import requests

from backend.application.ports.market_data_provider import MarketDataProvider
from backend.domain.entities.security import (
    Bar,
    GlobalRates,
    Profile,
    Quote,
    SecurityType,
)
from backend.infra.adapters.rate_limiter import RateLimiter, RateLimiterConfig


logger = logging.getLogger(__name__)


@dataclass
class FMPConfig:
    api_key: str
    base_url: str = "https://financialmodelingprep.com/stable"
    timeout_sec: float = 10.0
    default_days_back: int = 365
    rate_limiter: RateLimiterConfig = field(
        default_factory=lambda: RateLimiterConfig(max_per_minute=100)
    )


class FMPClient(MarketDataProvider):
    """
    Thin client over the FinancialModelingPrep API.

    All HTTP calls go through `_get`, which:
      - Throttles via a `RateLimiter` (hybrid sliding window + token bucket)
      - Retries on 429 with exponential backoff (up to 3 retries)
      - Raises for any other HTTP errors
      - Returns parsed JSON
    """

    def __init__(self, config: FMPConfig):
        self.cfg = config
        self._rate_limiter = RateLimiter(config.rate_limiter)

    def _redact(self, text: str) -> str:
        """Redact the apikey query parameter value from any string."""
        return re.sub(r"(?i)([?&]apikey=)[^&\s]*", r"\1***", text)

    def _raise_sanitized(self, resp: requests.Response) -> None:
        """Call raise_for_status() and re-raise with the API key redacted."""
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # `from None` suppresses the exception chain so the original
            # (unredacted) URL doesn't appear in tracebacks.
            raise requests.exceptions.HTTPError(self._redact(str(e))) from None

    def _get(
        self, url: str, params: dict[str, Any] | None = None, *, max_retries: int = 3
    ) -> Any:
        """
        Perform a GET request with rate limiting and exponential backoff on 429.

        Returns parsed JSON on success.
        Raises requests.exceptions.HTTPError on non-OK responses (after retries).
        Raises ValueError if response body is not valid JSON.
        """
        attempt = 0

        while True:
            # Reserve rate-limit slot before issuing the HTTP request
            self._rate_limiter.acquire_slot()
            try:
                resp = requests.get(
                    url,
                    params=params,
                    timeout=self.cfg.timeout_sec,
                )
            except requests.exceptions.RequestException as e:
                raise type(e)(self._redact(str(e))) from None

            # Too Many Requests – retry with backoff
            if resp.status_code == 429:
                attempt += 1
                retry_after_raw = resp.headers.get("Retry-After", "5")
                try:
                    retry_after = int(retry_after_raw)
                except ValueError:
                    retry_after = 5

                logger.warning(
                    "FMP 429 Too Many Requests for %s, attempt %d/%d, "
                    "Retry-After=%s, body=%s",
                    self._redact(resp.url),
                    attempt,
                    max_retries,
                    retry_after_raw,
                    self._redact(resp.text[:200]),
                )

                if attempt > max_retries:
                    # Give up and raise the HTTPError
                    self._raise_sanitized(resp)

                # Handle rate limit with exponential backoff
                self._rate_limiter.handle_rate_limit(retry_after, attempt)
                continue  # retry loop

            # Other HTTP errors
            self._raise_sanitized(resp)

            # Parse JSON
            try:
                return resp.json()
            except ValueError as e:
                logger.error(
                    "Invalid JSON from FMP for %s: %s", self._redact(resp.url), e
                )
                raise

    def fetch_quote(self, symbol: str) -> Quote:
        url = f"{self.cfg.base_url}/quote"
        params = {"symbol": symbol, "apikey": self.cfg.api_key}

        try:
            data = self._get(url, params=params)
        except requests.exceptions.HTTPError as e:
            logger.error("Error retrieving quote for %s: %s", symbol, e)
            raise

        item = data[0]
        return Quote(
            symbol=symbol,
            name=item.get("name", ""),
            exchange=item.get("exchange", ""),
            open=item.get("open", 0.0),
            high=item.get("dayHigh", 0.0),
            low=item.get("dayLow", 0.0),
            close=item.get("price", 0.0),
            currency="CAD" if symbol.endswith(".TO") else "USD",
            volume=item.get("volume", 0.0),
            change=item.get("change", 0.0),
            change_percent=item.get("changePercentage", 0.0) / 100.0,
            previousClose=item.get("previousClose", 0.0),
            timestamp=item.get("timestamp", datetime.now()),
        )

    def fetch_batch_quotes(self, symbols: list[str]) -> list[Quote]:
        url = f"{self.cfg.base_url}/batch-quote"
        params = {"symbols": ",".join(symbols), "apikey": self.cfg.api_key}
        try:
            data = self._get(url, params=params)
        except requests.exceptions.HTTPError as e:
            logger.error("Error retrieving batch quotes for %s: %s", symbols, e)
            raise
        if not data:
            logger.warning(
                "No batch quotes data retrieved for symbols %s",
                symbols,
            )
            raise ValueError("No batch quotes data retrieved for symbols %s", symbols)
        return [
            Quote(
                symbol=item.get("symbol", ""),
                name=item.get("name", ""),
                exchange=item.get("exchange", ""),
                open=item.get("open", 0.0),
                high=item.get("dayHigh", 0.0),
                low=item.get("dayLow", 0.0),
                close=item.get("price", 0.0),
                currency="CAD" if item.get("symbol", "").endswith(".TO") else "USD",
                volume=item.get("volume", 0.0),
                change=item.get("change", 0.0),
                change_percent=item.get("changePercentage", 0.0) / 100.0,
                previousClose=item.get("previousClose", 0.0),
                timestamp=item.get("timestamp", datetime.now()),
            )
            for item in data
        ]

    def fetch_bars(
        self,
        symbol: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Bar]:
        url = f"{self.cfg.base_url}/historical-price-eod/full"
        params = {
            "symbol": symbol,
            "apikey": self.cfg.api_key,
            "from": from_date.strftime("%Y-%m-%d")
            if from_date is not None
            else (date.today() - timedelta(days=self.cfg.default_days_back)).strftime(
                "%Y-%m-%d"
            ),
            "to": to_date.strftime("%Y-%m-%d")
            if to_date is not None
            else date.today().strftime("%Y-%m-%d"),
        }

        try:
            data = self._get(url, params=params)
        except requests.exceptions.HTTPError as e:
            logger.error("Error retrieving bars for %s: %s", symbol, e)
            raise

        if not isinstance(data, list) or not data:
            logger.error("No bars data retrieved for symbol %s", symbol)
            raise ValueError("No bars data retrieved for symbol %s", symbol)

        bars = [
            Bar(
                symbol=symbol,
                date=bar.get("date", ""),
                open=bar.get("open", ""),
                high=bar.get("high", ""),
                low=bar.get("low", ""),
                close=bar.get("close", ""),
                volume=bar.get("volume", ""),
            )
            for bar in data
        ]

        # FTRK-205: ensure oldest first
        return bars[::-1]

    def fetch_global_rates(self) -> GlobalRates:
        # 1) Treasury rates
        url = f"{self.cfg.base_url}/treasury-rates"
        params = {"apikey": self.cfg.api_key}

        try:
            data = self._get(url, params=params)
        except requests.exceptions.HTTPError as e:
            logger.error("Error retrieving treasury rates: %s", e)
            raise

        if not isinstance(data, list) or not data:
            logger.warning("No treasury rates data retrieved")
            raise ValueError("No treasury rates data retrieved")

        date = data[0].get("date", "")
        rf_rate = data[0].get("month6", "")  # use 6-month rate

        # 2) FX quote for USDCAD
        url = f"{self.cfg.base_url}/quote"
        params = {"symbol": "USDCAD", "apikey": self.cfg.api_key}

        try:
            data = self._get(url, params=params)
        except requests.exceptions.HTTPError as e:
            logger.error("Error retrieving FX quote for USDCAD: %s", e)
            raise

        if not data:
            logger.warning("No quote data retrieved for symbol USDCAD")
            raise ValueError("No quote data retrieved for symbol USDCAD")

        fx_rate = data[0].get("price", "")

        return GlobalRates(
            date=date,
            rf_rate=rf_rate,
            fx_rate=fx_rate,
        )

    def fetch_stock_profile(self, symbol: str) -> Profile:
        url = f"{self.cfg.base_url}/profile"
        params = {"symbol": symbol, "apikey": self.cfg.api_key}

        try:
            data = self._get(url, params=params)
        except requests.exceptions.HTTPError as e:
            logger.warning("Profile request failed for %s: %s", symbol, e)
            raise

        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            logger.warning("No profile data retrieved for symbol %s", symbol)
            raise ValueError("No profile data retrieved for symbol %s" % symbol)

        item = data[0]
        range_str = item.get("range", None)
        yearHigh = yearLow = None
        if range_str is not None:
            try:
                low_str, high_str = range_str.split("-")
                yearLow = float(low_str)
                yearHigh = float(high_str)
            except Exception:
                yearHigh = yearLow = None

        return Profile(
            symbol=symbol,
            date=datetime.now(timezone.utc),
            name=item.get("companyName", ""),
            type=SecurityType.ETF if item.get("isEtf", False) else SecurityType.STOCK,
            exchange=item.get("exchange", ""),
            currency=item.get("currency", ""),
            marketCap=item.get("marketCap", 0.0),
            beta=item.get("beta", 0.0),
            lastDividend=item.get("lastDividend", 0.0),
            averageVolume=item.get("averageVolume", 0.0),
            yearHigh=yearHigh,
            yearLow=yearLow,
            isin=item.get("isin", ""),
            cusip=item.get("cusip", ""),
            industry=item.get("industry", ""),
            sector=item.get("sector", ""),
            country=item.get("country", ""),
        )
