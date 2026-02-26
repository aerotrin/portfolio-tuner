import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Callable, List, Optional

from backend.application.ports.market_data_provider import MarketDataProvider
from backend.application.ports.market_data_repo import MarketDataRepository
from backend.domain.aggregates.security import Security
from backend.domain.entities.security import (
    Bar,
    BarsSyncState,
    GlobalRates,
    PerformanceMetric,
    Profile,
    Quote,
    SecurityAnalyticsResponse,
    TimeseriesIndicator,
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

    async def refresh_profiles_async(
        self,
        symbols: list[str],
        max_concurrency: int = 10,
        force: bool = False,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not symbols:
            return

        existing_syms = {p.symbol for p in self.db.read_profiles(symbols)}
        pending = [s for s in symbols if force or s not in existing_syms]

        if not pending:
            return

        semaphore = asyncio.Semaphore(max_concurrency)
        profiles: list[Profile] = []

        async def fetch_one(symbol: str) -> None:
            async with semaphore:
                profile: Profile | None = None
                # Tier 1: Primary
                try:
                    profile = await asyncio.to_thread(
                        self.ds_primary.fetch_stock_profile, symbol
                    )
                except Exception:
                    logger.warning(
                        "Profile fetch failed for %s on primary. Trying secondary.",
                        symbol,
                    )
                    # Tier 2: Secondary
                    try:
                        profile = await asyncio.to_thread(
                            self.ds_backup.fetch_stock_profile, symbol
                        )
                    except Exception:
                        logger.error(
                            "Profile fetch failed for %s on secondary. Giving up.",
                            symbol,
                        )

                if profile is not None:
                    profiles.append(profile)

        await asyncio.gather(*[fetch_one(s) for s in pending])

        if profiles:
            self.db.upsert_profiles_batch(profiles)

    async def refresh_bars_async(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_concurrency: int = 10,
        force: bool = False,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not symbols:
            return

        today = datetime.now(tz=timezone.utc).date()
        yesterday = today - timedelta(days=1)
        effective_end = yesterday
        fetch_start_fallback = start_date or (today - timedelta(days=365))

        # 1. Load sync states in a single query
        sync_states = self.db.read_bars_sync_states(symbols)

        # 2. Smart identify symbols that need to be fetched
        pending: list[tuple[str, date, date]] = []  # (symbol, fetch_start, fetch_end)

        for symbol in symbols:
            state = sync_states[symbol]
            if (
                not force
                and state.last_checked_at
                and state.last_checked_at.date() == today
            ):
                continue  # already evaluated today — skip entirely, no write
            if force or state.last_bar_date is None:
                pending.append((symbol, fetch_start_fallback, effective_end))
            elif state.last_bar_date < yesterday:
                pending.append(
                    (symbol, state.last_bar_date + timedelta(days=1), effective_end)
                )
            # else: bars already current, nothing to fetch

        # 3. Fetch pending symbols concurrently (thread-pool + semaphore)
        now = datetime.now(tz=timezone.utc)

        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_one(symbol: str, fetch_start: date, fetch_end: date) -> None:
            async with semaphore:
                bars: list[Bar] | None = None
                try:
                    bars = await asyncio.to_thread(
                        self.ds_primary.fetch_bars, symbol, fetch_start, fetch_end
                    )
                except Exception:
                    logger.warning(
                        "Bars fetching failed for %s on primary. Trying alternate.",
                        symbol,
                    )
                    try:
                        bars = await asyncio.to_thread(
                            self.ds_backup.fetch_bars, symbol, fetch_start, fetch_end
                        )
                    except Exception:
                        logger.error(
                            "Bars fetching failed for %s on alternate. Logging as error.",
                            symbol,
                        )
                        self.db.upsert_bars_sync_states(
                            [
                                BarsSyncState(
                                    symbol=symbol,
                                    status="error",
                                    last_checked_at=now,
                                    last_bar_date=sync_states[symbol].last_bar_date,
                                    last_success_at=sync_states[symbol].last_success_at,
                                )
                            ]
                        )
                        return

                if not bars:
                    # No new data for the range (e.g. non-trading day) — still ok
                    self.db.upsert_bars_sync_states(
                        [
                            BarsSyncState(
                                symbol=symbol,
                                status="ok",
                                last_checked_at=now,
                                last_bar_date=sync_states[symbol].last_bar_date,
                                last_success_at=sync_states[symbol].last_success_at,
                            )
                        ]
                    )
                    return

                new_last_bar = max(b.date for b in bars)
                self.db.upsert_bars_sync_states(
                    [
                        BarsSyncState(
                            symbol=symbol,
                            status="ok",
                            last_checked_at=now,
                            last_success_at=now,
                            last_bar_date=new_last_bar,
                        )
                    ]
                )
                self.db.upsert_bars(bars)

        await asyncio.gather(*[fetch_one(s, fs, fe) for s, fs, fe in pending])

        # 5. Trim all symbols to requested window
        if start_date:
            self.db.trim_bars_batch(symbols, before_date=start_date)

        # 6. Report progress
        if on_progress:
            for symbol in symbols:
                try:
                    on_progress(symbol)
                except Exception:
                    pass

    async def refresh_quotes_async(
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
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_batch(batch: list[str]) -> tuple[list[str], list[Quote]]:
            async with semaphore:
                # Tier 1: Primary batch
                try:
                    quotes = await asyncio.to_thread(
                        self.ds_primary.fetch_batch_quotes, batch
                    )
                    return batch, quotes
                except Exception:
                    logger.warning(
                        "Quotes batch fetching failed on primary. Trying alternate batch",
                    )

                # Tier 2: Secondary batch
                try:
                    quotes = await asyncio.to_thread(
                        self.ds_backup.fetch_batch_quotes, batch
                    )
                    return batch, quotes
                except Exception:
                    logger.warning(
                        "Quotes batch fetching failed on alternate. Will retry per-symbol",
                    )

                return batch, []

        all_quotes: list[Quote] = []
        all_symbols: list[str] = []

        tasks = {asyncio.create_task(fetch_batch(b)): b for b in batches}
        for completed_task in asyncio.as_completed(tasks.keys()):
            current_batch: list[str] | None = None
            returned_quotes: list[Quote] = []
            try:
                current_batch, returned_quotes = await completed_task
                returned_syms = {q.symbol for q in returned_quotes}
                missed = set(current_batch) - returned_syms

                # --- Single-fetch retry for missed symbols ---
                for symbol in missed:
                    quote: Quote | None = None

                    # Tier 3: Primary single
                    try:
                        quote = await asyncio.to_thread(
                            self.ds_primary.fetch_quote, symbol
                        )
                    except Exception:
                        logger.warning(
                            "%s quote fetch failed on primary. Trying alternate",
                            symbol,
                        )

                    # Tier 4: Secondary single
                    if quote is None:
                        try:
                            quote = await asyncio.to_thread(
                                self.ds_backup.fetch_quote, symbol
                            )
                        except Exception:
                            logger.error(
                                "%s quote fetch failed on alternate. Giving up.",
                                symbol,
                            )

                    if quote is not None:
                        returned_quotes.append(quote)
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

        self.db.upsert_quotes_batch(all_quotes)

        for sym in all_symbols:
            if on_progress:
                try:
                    on_progress(sym)
                except Exception:
                    pass

    async def refresh_securities_async(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        force: bool = False,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Refresh global rates, quotes, and bars concurrently for all symbols."""
        self.refresh_global_rates()
        await asyncio.gather(
            self.refresh_quotes_async(
                symbols,
                batch_size=100,
                max_concurrency=max_concurrency,
                on_progress=None,  # bars owns progress tracking
            ),
            self.refresh_bars_async(
                symbols,
                start_date=start_date,
                end_date=end_date,
                max_concurrency=max_concurrency,
                force=force,
                on_progress=on_progress,
            ),
            self.refresh_profiles_async(
                symbols,
                max_concurrency=max_concurrency,
                force=force,
            ),
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
