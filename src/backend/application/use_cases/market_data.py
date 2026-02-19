import asyncio
from datetime import date
import logging
from typing import Callable, List, Optional

from backend.application.ports.market_data_provider import MarketDataProvider
from backend.application.ports.market_data_repo import MarketDataRepository
from backend.domain.aggregates.security import Security
from backend.domain.entities.security import (
    Bar,
    GlobalRates,
    PerformanceMetric,
    Profile,
    Quote,
    TimeseriesIndicator,
    SecurityType,
)

logger = logging.getLogger(__name__)


class MarketDataManager:
    """Use cases for managing market data from external providers."""

    def __init__(
        self,
        ds_us: MarketDataProvider,
        ds_ca: MarketDataProvider,
        db: MarketDataRepository,
    ):
        self.ds_us = ds_us
        self.ds_ca = ds_ca
        self.db = db

    def _datasource_router(self, symbol: str) -> MarketDataProvider:
        if symbol.endswith(".TO"):
            return self.ds_ca
        else:
            return self.ds_us

    def _profile_fixer(self, quote: Quote, profile: Profile) -> Profile:
        # FTRK-351 infer missing profile fields from quote, if not present
        if profile.type == SecurityType.UNKNOWN:
            if "ETF" in quote.name:
                profile.type = SecurityType.ETF
            elif "INDEX" in quote.exchange:
                profile.type = SecurityType.INDEX
            elif "COMMODITY" in quote.exchange:
                profile.type = SecurityType.COMMODITY
            elif "CRYPTO" in quote.exchange:
                profile.type = SecurityType.CRYPTO
            elif "FOREX" in quote.exchange:
                profile.type = SecurityType.FOREX
            profile.name = quote.name
            profile.exchange = quote.exchange
            profile.currency = quote.currency
            logger.info(f"Inferred profile fields from quote for {quote.symbol}")
        return profile

    def _bars_fixer(self, quote: Quote, bars: list[Bar]) -> list[Bar]:
        bars.append(
            Bar(
                symbol=quote.symbol,
                date=quote.timestamp,
                open=quote.open,
                high=quote.high,
                low=quote.low,
                close=quote.close,
                volume=quote.volume,
            )
        )
        return bars

    # --- Write / ETL use cases ---

    def fetch_quote(
        self,
        symbol: str,
    ) -> Quote:
        ds = self._datasource_router(symbol)
        quote = ds.fetch_quote(symbol)

        return quote

    def fetch_security_data(
        self,
        symbol: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> tuple[Quote, list[Bar], Profile]:
        ds = self._datasource_router(symbol)

        quote = ds.fetch_quote(symbol)
        bars = ds.fetch_bars(symbol, start_date, end_date)
        profile = self.ds_us.fetch_stock_profile(
            symbol
        )  # always use US datasource for profile
        profile = self._profile_fixer(quote, profile)
        bars = self._bars_fixer(quote, bars)

        return quote, bars, profile

    def refresh_global_rates(self):
        self.db.upsert_global_rates(self.ds_us.fetch_global_rates())

    def refresh_security(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        ds = self._datasource_router(symbol)
        quote = ds.fetch_quote(symbol)
        bars = ds.fetch_bars(symbol, start_date, end_date)
        profile = self.ds_us.fetch_stock_profile(
            symbol
        )  # always use US datasource for profile
        profile = self._profile_fixer(quote, profile)

        self.db.upsert_quote(quote)
        self.db.upsert_bars(bars)
        self.db.upsert_profile(profile)

    async def refresh_securities_async(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not symbols:
            return

        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_one(symbol: str):
            # limit concurrent workers
            await sem.acquire()
            try:
                # run blocking HTTP work in a thread
                quote, bars, profile = await asyncio.to_thread(
                    self.fetch_security_data, symbol, start_date, end_date
                )
                return symbol, quote, bars, profile
            finally:
                sem.release()

        # 1) fetch all data concurrently, process as they complete
        tasks = {asyncio.create_task(fetch_one(sym)): sym for sym in symbols}
        for completed_task in asyncio.as_completed(tasks.keys()):
            symbol = None
            try:
                symbol, quote, bars, profile = await completed_task
                # 2) write to DB sequentially (single thread)
                self.db.upsert_quote(quote)
                self.db.upsert_bars(bars)
                self.db.upsert_profile(profile)
            except Exception:
                # If we don't have the symbol yet, try to get it from the task mapping
                if symbol is None:
                    # Type cast to handle type checker - asyncio.as_completed returns the same tasks
                    symbol = tasks.get(completed_task)  # type: ignore
                raise
            finally:
                # Report progress after each symbol is processed (success or failure)
                if on_progress and symbol:
                    try:
                        on_progress(symbol)
                    except Exception:
                        # Don't let progress callback errors break the refresh
                        pass

    async def refresh_securities_intraday_async(
        self,
        symbols: list[str],
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not symbols:
            return

        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_one(symbol: str):
            # limit concurrent workers
            await sem.acquire()
            try:
                # run blocking HTTP work in a thread
                quote = await asyncio.to_thread(self.fetch_quote, symbol)
                return symbol, quote
            finally:
                sem.release()

        # 1) fetch all data concurrently, process as they complete
        tasks = {asyncio.create_task(fetch_one(sym)): sym for sym in symbols}
        for completed_task in asyncio.as_completed(tasks.keys()):
            symbol = None
            try:
                symbol, quote = await completed_task
                # 2) write to DB sequentially (single thread)
                self.db.upsert_quote(quote)
            except Exception:
                # If we don't have the symbol yet, try to get it from the task mapping
                if symbol is None:
                    # Type cast to handle type checker - asyncio.as_completed returns the same tasks
                    symbol = tasks.get(completed_task)  # type: ignore
                raise
            finally:
                # Report progress after each symbol is processed (success or failure)
                if on_progress and symbol:
                    try:
                        on_progress(symbol)
                    except Exception:
                        # Don't let progress callback errors break the refresh
                        pass

    # --- Aggregate building helpers ---
    def build_security(self, symbol: str) -> Security:
        quote = self.get_security_quote(symbol)
        bars = self.get_security_bars(symbol)
        profile = self.get_security_profile(symbol)
        rates = self.get_global_rates()
        if quote is None or bars is None or profile is None or rates is None:
            raise ValueError(f"Security data missing for symbol: {symbol}")
        return Security(quote=quote, bars=bars, profile=profile, rates=rates)

    # --- Read / view-model use cases ---

    def get_global_rates(self) -> GlobalRates | None:
        rates = self.db.read_global_rates()
        if rates is None:  # first time, refresh from external source
            self.refresh_global_rates()
            rates = self.db.read_global_rates()
        return rates

    def get_available_symbols(self) -> List[str]:
        return self.db.read_securities_list()

    def get_security_quote(self, symbol: str) -> Quote | None:
        return self.db.read_quote(symbol)

    def get_security_quotes(self, symbols: list[str]) -> list[Quote]:
        return self.db.read_quotes(symbols)

    def get_security_bars(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[Bar]:
        return self.db.read_bars(symbol, start_date, end_date)

    def get_security_batch_bars(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, list[Bar]]:
        return {
            symbol: self.db.read_bars(symbol, start_date, end_date)
            for symbol in symbols
        }

    def get_security_profile(self, symbol: str) -> Profile | None:
        return self.db.read_profile(symbol)

    def get_security_profiles(self, symbols: list[str]) -> list[Profile]:
        return self.db.read_profiles(symbols)

    def get_security_metrics(self, symbol: str) -> PerformanceMetric:
        return self.build_security(symbol).metrics

    def get_security_batch_metrics(self, symbols: list[str]) -> list[PerformanceMetric]:
        return [self.build_security(symbol).metrics for symbol in symbols]

    def get_security_indicators(self, symbol: str) -> List[TimeseriesIndicator]:
        return self.build_security(symbol).indicators

    def get_security_batch_indicators(
        self, symbols: list[str]
    ) -> dict[str, list[TimeseriesIndicator]]:
        return {symbol: self.build_security(symbol).indicators for symbol in symbols}
