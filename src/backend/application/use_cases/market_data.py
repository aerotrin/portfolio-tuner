import asyncio
from datetime import date
import logging
import time
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
    SecurityAnalyticsResponse,
    TimeseriesIndicator,
    SecurityType,
)

logger = logging.getLogger(__name__)


class MarketDataManager:
    """Use cases for managing market data from external providers."""

    def __init__(
        self,
        ds_primary: MarketDataProvider,
        ds_backup: MarketDataProvider,
        db: MarketDataRepository,
    ):
        self.ds_primary = ds_primary
        self.ds_backup = ds_backup  # retained but unused; reserved for future failover
        self.db = db

    # Helper methods

    # TODO: Deprecate this
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

    # --- DS passthrough use cases ---

    def fetch_quote(
        self,
        symbol: str,
    ) -> Quote:
        quote = self.ds_primary.fetch_quote(symbol)

        return quote

    def fetch_bars(
        self,
        symbol: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> list[Bar]:
        bars = self.ds_primary.fetch_bars(symbol, start_date, end_date)
        return bars

    def fetch_profile(
        self,
        symbol: str,
    ) -> Profile:
        profile = self.ds_primary.fetch_stock_profile(symbol)
        return profile

    # --- Sync to DB use cases ---

    def refresh_global_rates(self):
        self.db.upsert_global_rates(self.ds_primary.fetch_global_rates())

    async def refresh_batch_profiles_async(
        self,
        symbols: list[str],
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        # TODO: Implement smart updating logic of profiles
        pass

    async def refresh_batch_bars_async(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        # TODO: Implement smart updating logic of bars
        pass

    async def refresh_batch_quotes_async(
        self,
        symbols: list[str],
        batch_size: int = 100,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not symbols:
            return

        batches = [
            symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)
        ]
        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_batch(batch: list[str]) -> tuple[list[str], list[Quote]]:
            await sem.acquire()
            try:
                t0 = time.perf_counter()
                quotes = await asyncio.to_thread(
                    self.ds_primary.fetch_batch_quotes, batch
                )
                elapsed = time.perf_counter() - t0
                logger.info(
                    "fetch_batch_quotes: %d symbols in %.3fs",
                    len(batch),
                    elapsed,
                )
                return batch, quotes
            except Exception:
                logger.warning(
                    "fetch_batch_quotes failed for batch of %d symbols; falling back to single fetches",
                    len(batch),
                    exc_info=True,
                )
                return batch, []
            finally:
                sem.release()

        all_quotes: list[Quote] = []
        all_bars: list[Bar] = []
        all_symbols: list[str] = []

        tasks = {asyncio.create_task(fetch_batch(b)): b for b in batches}
        for completed_task in asyncio.as_completed(tasks.keys()):
            current_batch: list[str] | None = None
            returned_quotes: list[Quote] = []
            try:
                current_batch, returned_quotes = await completed_task
                returned_syms = {q.symbol for q in returned_quotes}
                missed = set(current_batch) - returned_syms

                # --- Single-fetch retry with backup datasource for missed symbols ---
                for symbol in missed:
                    try:
                        logger.info(f"Fetching backup quote for symbol: {symbol}")
                        quote = await asyncio.to_thread(
                            self.ds_backup.fetch_quote, symbol
                        )
                        returned_quotes.append(quote)
                    except Exception:
                        logger.warning(
                            "Single-fetch retry failed for symbol %s; skipping",
                            symbol,
                        )

                    try:
                        logger.info(f"Fetching backup bars for symbol: {symbol}")
                        bars = await asyncio.to_thread(
                            self.ds_backup.fetch_bars, symbol
                        )
                        all_bars.extend(bars)
                    except Exception:
                        logger.warning(
                            "Backup fetch_bars failed for symbol %s; skipping",
                            symbol,
                        )

                all_quotes.extend(returned_quotes)
            except Exception:
                if current_batch is None:
                    current_batch = tasks.get(completed_task)  # type: ignore
                raise
            finally:
                batch_for_progress = (
                    current_batch or tasks.get(completed_task) or []  # type: ignore
                )
                all_symbols.extend(batch_for_progress)

        t1 = time.perf_counter()
        self.db.upsert_quotes_batch(all_quotes)
        logger.info(
            "upsert_quotes_batch: %d quotes in %.3fs",
            len(all_quotes),
            time.perf_counter() - t1,
        )

        if all_bars:
            t2 = time.perf_counter()
            self.db.upsert_bars(all_bars)
            logger.info(
                "upsert_bars (backup): %d bars in %.3fs",
                len(all_bars),
                time.perf_counter() - t2,
            )

        for sym in all_symbols:
            if on_progress:
                try:
                    on_progress(sym)
                except Exception:
                    pass

    async def refresh_securities_batch_async(
        self,
        symbols: list[str],
        intraday: bool,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Refresh global rates then all securities — intraday (quotes only) or EOD (full bars)."""
        self.refresh_global_rates()
        if intraday:
            await self.refresh_batch_quotes_async(
                symbols,
                batch_size=100,
                max_concurrency=max_concurrency,
                on_progress=on_progress,
            )
        else:
            await self.refresh_batch_bars_async(
                symbols,
                start_date=start_date,
                end_date=end_date,
                max_concurrency=max_concurrency,
                on_progress=on_progress,
            )
            await self.refresh_batch_profiles_async(
                symbols,
                max_concurrency=max_concurrency,
                on_progress=on_progress,
            )

    # --- Read raw use cases ---

    def read_global_rates(self) -> GlobalRates:
        rates = self.db.read_global_rates()
        if rates is None:  # first time, refresh from external source
            self.refresh_global_rates()
            rates = self.db.read_global_rates()
        return rates

    def read_available_symbols(self) -> List[str]:
        return self.db.read_securities_list()

    def read_security_quote(self, symbol: str) -> Quote | None:
        return self.db.read_quote(symbol)

    def read_security_batch_quotes(self, symbols: list[str]) -> list[Quote]:
        return self.db.read_quotes(symbols)

    def read_security_bars(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[Bar]:
        return self.db.read_bars(symbol, start_date, end_date)

    def read_security_batch_bars(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, list[Bar]]:
        return self.db.read_batch_bars(symbols, start_date, end_date)

    def read_security_profile(self, symbol: str) -> Profile | None:
        return self.db.read_profile(symbol)

    def read_security_batch_profiles(self, symbols: list[str]) -> list[Profile]:
        return self.db.read_profiles(symbols)

    # --- Compute security analytics use cases ---
    def _build_security(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        rates: Optional[GlobalRates] = None,
    ) -> Security:
        quote = self.read_security_quote(symbol)
        bars = self.read_security_bars(symbol, start_date, end_date)
        profile = self.read_security_profile(symbol)
        if rates is None:
            rates = self.read_global_rates()
        if quote is None or bars is None or rates is None:
            raise ValueError(f"Security data missing for symbol: {symbol}")
        return Security(quote=quote, bars=bars, profile=profile, rates=rates)

    async def build_securities_batch_async(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        rates: Optional[GlobalRates] = None,
    ) -> dict[str, Security]:
        if not symbols:
            return {}
        if rates is None:
            rates = await asyncio.to_thread(self.read_global_rates)
        quotes_list, bars_map, profiles_list = await asyncio.gather(
            asyncio.to_thread(self.db.read_quotes, symbols),
            asyncio.to_thread(self.db.read_batch_bars, symbols, start_date, end_date),
            asyncio.to_thread(self.db.read_profiles, symbols),
        )
        quotes = {q.symbol: q for q in quotes_list}
        profiles = {p.symbol: p for p in profiles_list}

        def build_one(symbol: str) -> tuple[str, Security]:
            quote = quotes.get(symbol)
            profile = profiles.get(symbol)
            if quote is None or rates is None:
                raise ValueError(f"Security data missing for symbol: {symbol}")
            return symbol, Security(
                quote=quote,
                bars=bars_map.get(symbol, []),
                profile=profile,
                rates=rates,
            )

        pairs = await asyncio.gather(
            *[asyncio.to_thread(build_one, sym) for sym in symbols]
        )
        return dict(pairs)

    def compute_security_metrics(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PerformanceMetric:
        return self._build_security(symbol, start_date, end_date).metrics

    async def compute_security_batch_metrics(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PerformanceMetric]:
        securities = await self.build_securities_batch_async(
            symbols, start_date, end_date
        )
        return [
            securities[symbol].metrics for symbol in symbols if symbol in securities
        ]

    def compute_security_indicators(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[TimeseriesIndicator]:
        return self._build_security(symbol, start_date, end_date).indicators

    async def compute_security_batch_indicators(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, list[TimeseriesIndicator]]:
        securities = await self.build_securities_batch_async(
            symbols, start_date, end_date
        )
        return {
            symbol: securities[symbol].indicators
            for symbol in symbols
            if symbol in securities
        }

    async def compute_security_batch_analytics(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, SecurityAnalyticsResponse]:
        securities = await self.build_securities_batch_async(
            symbols, start_date, end_date
        )
        result: dict[str, SecurityAnalyticsResponse] = {}
        for symbol, sec in securities.items():
            result[symbol] = SecurityAnalyticsResponse(
                quote=sec.quote,
                profile=sec.profile,
                bars=sec.bars,
                metrics=sec.metrics,
                indicators=sec.indicators,
            )
        return result
