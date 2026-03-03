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
        ds_backup: Optional[MarketDataProvider],
        db: MarketDataRepository,
    ):
        self.ds_primary = ds_primary
        self.ds_backup = ds_backup
        self.db = db

    # --- DS direct-fetch use cases ---
    def fetch_single_quote(self, symbol: str) -> Quote | None:
        try:
            return self.ds_primary.fetch_quote(symbol)
        except Exception:
            if self.ds_backup is None:
                logger.error("Failed to fetch single quote for %s. Giving up.", symbol)
                return None
            try:
                return self.ds_backup.fetch_quote(symbol)
            except Exception:
                logger.error("Failed to fetch single quote for %s. Giving up.", symbol)
                return None

    def fetch_single_profile(self, symbol: str) -> Profile | None:
        try:
            return self.ds_primary.fetch_stock_profile(symbol)
        except Exception:
            if self.ds_backup is None:
                logger.error(
                    "Failed to fetch single profile for %s. Giving up.", symbol
                )
                return None
            try:
                return self.ds_backup.fetch_stock_profile(symbol)
            except Exception:
                logger.error(
                    "Failed to fetch single profile for %s. Giving up.", symbol
                )
                return None

    def fetch_single_bars(
        self, symbol: str, start_date: date | None = None, end_date: date | None = None
    ) -> list[Bar] | None:
        try:
            return self.ds_primary.fetch_bars(symbol, start_date, end_date)
        except Exception:
            if self.ds_backup is not None:
                try:
                    return self.ds_backup.fetch_bars(symbol, start_date, end_date)
                except Exception:
                    logger.error(
                        "Failed to fetch single bars for %s. Giving up.", symbol
                    )
                    return None
            else:
                logger.error("Failed to fetch single bars for %s. Giving up.", symbol)
                return None

    # --- Refresh and Sync to DB use cases -> Return Nothing---

    def refresh_global_rates(self):
        self.db.upsert_global_rates(self.ds_primary.fetch_global_rates())

    def pending_profiles(self, symbols: list[str], force: bool = False) -> list[str]:
        if not symbols:
            return []
        existing_syms = {p.symbol for p in self.db.read_profiles(symbols)}
        return [s for s in symbols if force or s not in existing_syms]

    def pending_bars(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        force: bool = False,
    ) -> tuple[list[tuple[str, date, date]], dict[str, BarsSyncState]]:
        if not symbols:
            return [], {}
        today = datetime.now(tz=timezone.utc).date()
        yesterday = today - timedelta(days=1)
        effective_end = yesterday
        fetch_start_fallback = start_date or (today - timedelta(days=365))
        sync_states = self.db.read_bars_sync_states(symbols)
        pending: list[tuple[str, date, date]] = []
        for symbol in symbols:
            state = sync_states[symbol]
            if (
                not force
                and state.last_checked_at
                and state.last_checked_at.date() == today
            ):
                continue  # already evaluated today — skip
            if force or state.last_bar_date is None:
                pending.append((symbol, fetch_start_fallback, effective_end))
            elif state.last_bar_date < yesterday:
                pending.append(
                    (symbol, state.last_bar_date + timedelta(days=1), effective_end)
                )
        pending_symbols = [s for s, _, _ in pending]
        sync_states_trimmed = {s: sync_states[s] for s in pending_symbols}
        return pending, sync_states_trimmed

    def pending_quotes(self, symbols: list[str]) -> list[str]:
        return list(symbols)  # no smart skip — always fetch all

    async def refresh_profiles_async(
        self,
        pending: list[str],
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not pending:
            return

        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_one(symbol: str) -> Profile | None:
            async with sem:
                try:
                    # Tier 1: Primary
                    try:
                        logger.debug("Fetching %s profile on primary...", symbol)
                        profile = await asyncio.to_thread(
                            self.ds_primary.fetch_stock_profile, symbol
                        )
                        return profile
                    except Exception:
                        logger.warning(
                            "Profile fetch failed for %s on primary.",
                            symbol,
                        )
                        # Tier 2: Secondary
                        if self.ds_backup is None:
                            return None

                        try:
                            logger.debug(
                                "Trying backup profile fetch for %s.",
                                symbol,
                            )
                            return await asyncio.to_thread(
                                self.ds_backup.fetch_stock_profile, symbol
                            )
                        except Exception:
                            logger.error(
                                "Backup profile fetch failed for %s. Giving up.",
                                symbol,
                            )
                            return None
                finally:
                    if on_progress:
                        try:
                            on_progress(symbol)
                        except Exception:
                            pass

        results = await asyncio.gather(*(fetch_one(s) for s in pending))
        profiles = [p for p in results if p is not None]
        if profiles:
            logger.debug("Starting DB upsert %d profiles", len(profiles))
            await asyncio.to_thread(self.db.upsert_profiles_batch, profiles)
            logger.debug("Finished DB upsert %d profiles", len(profiles))

    async def refresh_bars_async(
        self,
        pending: list[tuple[str, date, date]],
        sync_states: dict[str, BarsSyncState],
        trim_before_date: date | None = None,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not pending:
            return

        now = datetime.now(tz=timezone.utc)
        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_one(
            symbol: str, fetch_start: date, fetch_end: date
        ) -> list[Bar] | None:
            """Returns bars (possibly empty list), or None if all tiers failed."""
            async with sem:
                try:
                    bars: list[Bar] | None = None
                    try:
                        logger.debug("Fetching %s bars on primary...", symbol)
                        bars = await asyncio.to_thread(
                            self.ds_primary.fetch_bars, symbol, fetch_start, fetch_end
                        )
                    except Exception:
                        logger.warning(
                            "Bars fetching failed for %s on primary. Trying alternate.",
                            symbol,
                        )
                        # Tier 2: Secondary
                        if self.ds_backup is not None:
                            try:
                                logger.debug("Fetching %s bars on backup...", symbol)
                                bars = await asyncio.to_thread(
                                    self.ds_backup.fetch_bars,
                                    symbol,
                                    fetch_start,
                                    fetch_end,
                                )
                            except Exception:
                                logger.error(
                                    "Bars fetching failed for %s on alternate. Logging as error.",
                                    symbol,
                                )
                    return bars  # None = all tiers failed; [] = ok, no new data; [...] = ok
                finally:
                    if on_progress:
                        try:
                            on_progress(symbol)
                        except Exception:
                            pass

        results: list[list[Bar] | None] = await asyncio.gather(
            *(fetch_one(s, fs, fe) for s, fs, fe in pending)
        )

        # Batch all DB writes after gather
        sync_state_updates: list[BarsSyncState] = []
        bars_to_insert: list[Bar] = []
        for (symbol, _, _), bars in zip(pending, results):
            if bars is None:
                if sync_states[symbol].last_success_at is not None:
                    sync_state_updates.append(
                        BarsSyncState(
                            symbol=symbol,
                            status="error",
                            last_checked_at=now,
                            last_bar_date=sync_states[symbol].last_bar_date,
                            last_success_at=sync_states[symbol].last_success_at,
                        )
                    )
            else:
                new_last_bar = (
                    max(b.date for b in bars)
                    if bars
                    else sync_states[symbol].last_bar_date
                )
                sync_state_updates.append(
                    BarsSyncState(
                        symbol=symbol,
                        status="ok",
                        last_checked_at=now,
                        last_bar_date=new_last_bar,
                        last_success_at=now
                        if bars
                        else sync_states[symbol].last_success_at,
                    )
                )
                bars_to_insert.extend(bars)

        if sync_state_updates:
            logger.debug("Starting DB upsert %d sync states", len(sync_state_updates))
            await asyncio.to_thread(self.db.upsert_bars_sync_states, sync_state_updates)
            logger.debug("Finished DB upsert %d sync states", len(sync_state_updates))

        if bars_to_insert:
            logger.debug("Starting DB upsert %d bars", len(bars_to_insert))
            await asyncio.to_thread(self.db.upsert_bars, bars_to_insert)
            logger.debug("Finished DB upsert %d bars", len(bars_to_insert))

        if trim_before_date:
            succeeded = [
                sym for (sym, _, _), bars in zip(pending, results) if bars is not None
            ]
            if succeeded:
                logger.debug(
                    "Trimming bars before %s for %d symbols",
                    trim_before_date,
                    len(succeeded),
                )
                await asyncio.to_thread(
                    self.db.trim_bars_batch, succeeded, trim_before_date
                )
                logger.debug(
                    "Finished trimming bars before %s for %d symbols",
                    trim_before_date,
                    len(succeeded),
                )

    async def refresh_quotes_async(
        self,
        symbols: list[str],
        batch_size: int = 25,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not symbols:
            return

        batches = [
            symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)
        ]
        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_batch(batch: list[str]) -> list[Quote]:
            async with sem:
                try:
                    quotes: list[Quote] = []

                    # Tier 1: Primary batch
                    try:
                        logger.debug("Fetching %d quotes on primary...", len(batch))
                        quotes = await asyncio.to_thread(
                            self.ds_primary.fetch_batch_quotes, batch
                        )
                    except Exception:
                        logger.warning(
                            "Quotes batch fetching failed on primary for symbols: %s. Trying alternate.",
                            batch,
                        )

                    missed = [s for s in batch if s not in {q.symbol for q in quotes}]

                    # Tier 2: Secondary batch attempt
                    if self.ds_backup is not None and missed:
                        try:
                            logger.debug("Fetching %d quotes on backup...", len(missed))
                            backup_quotes = await asyncio.to_thread(
                                self.ds_backup.fetch_batch_quotes, missed
                            )
                            quotes = quotes + backup_quotes
                        except Exception:
                            logger.error(
                                "Quotes batch fetching failed on alternate. Giving up.",
                            )

                    still_missing = [
                        s for s in batch if s not in {q.symbol for q in quotes}
                    ]
                    if still_missing:
                        logger.error(
                            "Failed to fetch quotes for symbols: %s",
                            still_missing,
                        )

                    return quotes
                finally:
                    if on_progress:
                        for sym in batch:
                            try:
                                on_progress(sym)
                            except Exception:
                                pass

        results = await asyncio.gather(*(fetch_batch(b) for b in batches))

        all_quotes = [q for batch_quotes in results for q in batch_quotes]
        logger.debug("Starting DB upsert %d quotes", len(all_quotes))
        await asyncio.to_thread(self.db.upsert_quotes_batch, all_quotes)
        logger.debug("Finished DB upsert %d quotes", len(all_quotes))

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
        if quote is None or not bars or rates is None:
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
            rates = self.read_global_rates()
        quotes_list, bars_map, profiles_list = await asyncio.gather(
            asyncio.to_thread(self.db.read_quotes, symbols),
            asyncio.to_thread(self.db.read_batch_bars, symbols, start_date, end_date),
            asyncio.to_thread(self.db.read_profiles, symbols),
        )
        quotes = {q.symbol: q for q in quotes_list}
        profiles = {p.symbol: p for p in profiles_list}

        def build_one(symbol: str) -> Security:
            quote = quotes.get(symbol)
            profile = profiles.get(symbol)
            if quote is None:  # profile is optional, but quote is not
                raise ValueError(f"Security data missing for symbol: {symbol}")
            return Security(
                quote=quote,
                bars=bars_map.get(symbol, []),
                profile=profile,
                rates=rates,
            )

        return {sym: build_one(sym) for sym in symbols}

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
