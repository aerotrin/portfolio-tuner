import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Callable, List, Optional, Sequence

from backend.application.ports.market_data_provider import (
    MarketDataProvider,
    ProviderRateLimitError,
)
from backend.application.ports.market_data_repo import MarketDataRepository
from backend.domain.aggregates.security import Security
from backend.domain.analytics.price_chart import MAType, build_price_chart
from backend.domain.constants import PRICE_CHART_MA_PERIODS
from backend.domain.entities.security import (
    Bar,
    BarsSyncState,
    GlobalRates,
    PerformanceMetric,
    PriceChart,
    Profile,
    Quote,
    SecurityAnalyticsResponse,
    TimeseriesIndicator,
)

logger = logging.getLogger(__name__)

# A forced refresh re-fetches a profile only once it is this old
PROFILE_MAX_AGE_DAYS = 7

ANALYTICS_LOOKBACK_DAYS = 365
# Slack for weekends/holidays before a short stored history triggers a backfill
BACKFILL_GRACE_DAYS = 10


def _default_analytics_start() -> date:
    return datetime.now(tz=timezone.utc).date() - timedelta(
        days=ANALYTICS_LOOKBACK_DAYS
    )


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

    # --- Refresh and Sync to DB use cases ---
    # The async refreshers return the symbols they could not fetch.

    def refresh_global_rates(self):
        self.db.upsert_global_rates(self.ds_primary.fetch_global_rates())

    def pending_profiles(self, symbols: list[str], force: bool = False) -> list[str]:
        if not symbols:
            return []
        existing = {p.symbol: p for p in self.db.read_profiles(symbols)}
        if not force:
            return [s for s in symbols if s not in existing]
        # Profiles change slowly and cost several provider requests each
        stale_before = datetime.now(tz=timezone.utc) - timedelta(
            days=PROFILE_MAX_AGE_DAYS
        )

        def is_stale(profile: Profile) -> bool:
            fetched = profile.date
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            return fetched < stale_before

        return [s for s in symbols if s not in existing or is_stale(existing[s])]

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

        def checked_today(state: BarsSyncState) -> bool:
            return (
                state.last_checked_at is not None
                and state.last_checked_at.date() == today
            )

        to_evaluate = [s for s in symbols if force or not checked_today(sync_states[s])]
        backfill_candidates = (
            []
            if force
            else [s for s in to_evaluate if sync_states[s].last_bar_date is not None]
        )
        first_bar_dates = (
            self.db.read_first_bar_dates(backfill_candidates)
            if backfill_candidates
            else {}
        )
        backfill_cutoff = fetch_start_fallback + timedelta(days=BACKFILL_GRACE_DAYS)
        pending: list[tuple[str, date, date]] = []
        for symbol in to_evaluate:
            state = sync_states[symbol]
            if force or state.last_bar_date is None:
                pending.append((symbol, fetch_start_fallback, effective_end))
                continue
            first_bar_date = first_bar_dates.get(symbol)
            if first_bar_date is None or first_bar_date > backfill_cutoff:
                # Stored history is shorter than the window: re-fetch all of it,
                # since provider prices are adjusted as of fetch time
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
    ) -> list[str]:
        if not pending:
            return []

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
        return [s for s, p in zip(pending, results) if p is None]

    async def refresh_bars_async(
        self,
        pending: list[tuple[str, date, date]],
        sync_states: dict[str, BarsSyncState],
        trim_before_date: date | None = None,
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> list[str]:
        if not pending:
            return []

        now = datetime.now(tz=timezone.utc)
        sem = asyncio.Semaphore(max_concurrency)
        # Rate-limited symbols: the data may exist, so they are not recorded
        # as checked and the next refresh tries them again.
        rate_limited: set[str] = set()

        async def fetch_one(
            symbol: str, fetch_start: date, fetch_end: date
        ) -> list[Bar] | None:
            """Returns bars (possibly empty list), or None if all tiers failed."""
            async with sem:
                try:
                    bars: list[Bar] | None = None
                    try:
                        logger.debug(
                            "Fetching %s bars on primary from %s to %s",
                            symbol,
                            fetch_start,
                            fetch_end,
                        )
                        bars = await asyncio.to_thread(
                            self.ds_primary.fetch_bars, symbol, fetch_start, fetch_end
                        )
                    except Exception as primary_exc:
                        if isinstance(primary_exc, ProviderRateLimitError):
                            rate_limited.add(symbol)
                        logger.warning(
                            "Bars fetching failed for %s on primary. Trying alternate.",
                            symbol,
                        )
                        # Tier 2: Secondary
                        if self.ds_backup is not None:
                            try:
                                logger.debug(
                                    "Fetching %s bars on backup from %s to %s",
                                    symbol,
                                    fetch_start,
                                    fetch_end,
                                )
                                bars = await asyncio.to_thread(
                                    self.ds_backup.fetch_bars,
                                    symbol,
                                    fetch_start,
                                    fetch_end,
                                )
                                rate_limited.discard(symbol)
                            except Exception as backup_exc:
                                if isinstance(backup_exc, ProviderRateLimitError):
                                    rate_limited.add(symbol)
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
                if symbol in rate_limited:
                    continue
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
                        last_success_at=(
                            now if bars else sync_states[symbol].last_success_at
                        ),
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

        return [sym for (sym, _, _), bars in zip(pending, results) if bars is None]

    async def refresh_quotes_async(
        self,
        symbols: list[str],
        batch_size: int = 5,  # FTRK-496: provides smoother UI progress bar updating
        max_concurrency: int = 10,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> list[str]:
        if not symbols:
            return []

        batches = [
            symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)
        ]
        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_batch(batch: list[str]) -> list[Quote]:
            async with sem:
                quotes: list[Quote] = []
                try:
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
        fetched = {q.symbol for q in all_quotes}
        return [s for s in symbols if s not in fetched]

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
        if start_date is None:
            start_date = _default_analytics_start()
        quote = self.read_security_quote(symbol)
        bars = self.read_security_bars(symbol, start_date, end_date)
        profile = self.read_security_profile(symbol)
        if rates is None:
            rates = self.read_global_rates()
        if quote is None or rates is None:
            raise ValueError(f"Security data missing for symbol: {symbol}")
        if not bars:
            logger.debug("No bars for %s; building from quote only", symbol)
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
        if start_date is None:
            start_date = _default_analytics_start()
        if rates is None:
            rates = self.read_global_rates()
        quotes_list, bars_map, profiles_list = await asyncio.gather(
            asyncio.to_thread(self.db.read_quotes, symbols),
            asyncio.to_thread(self.db.read_batch_bars, symbols, start_date, end_date),
            asyncio.to_thread(self.db.read_profiles, symbols),
        )
        quotes = {q.symbol: q for q in quotes_list}
        profiles = {p.symbol: p for p in profiles_list}

        async def build_one(symbol: str) -> tuple[str, Security]:
            quote = quotes.get(symbol)
            bars = bars_map.get(symbol, [])
            profile = profiles.get(symbol)
            if quote is None:
                raise ValueError(f"Security data missing for symbol: {symbol}")
            # A newly listed security has a quote before its first daily bar
            if not bars:
                logger.debug("No bars for %s; building from quote only", symbol)
            sec = await asyncio.to_thread(
                Security, quote=quote, bars=bars, profile=profile, rates=rates
            )
            return symbol, sec

        pairs = await asyncio.gather(*[build_one(sym) for sym in symbols])
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

    def compute_security_price_chart(
        self,
        symbol: str,
        ma_type: MAType = "sma",
        ma_periods: Sequence[int] = PRICE_CHART_MA_PERIODS,
    ) -> PriceChart | None:
        """Daily chart over the full stored history; None for an unknown symbol."""
        return build_price_chart(
            symbol,
            self.read_security_bars(symbol),
            self.read_security_quote(symbol),
            self.read_security_profile(symbol),
            ma_type=ma_type,
            ma_periods=ma_periods,
        )
