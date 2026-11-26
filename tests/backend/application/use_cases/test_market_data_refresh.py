"""Refresh behaviour under provider failures and rate limits."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from backend.application.ports.market_data_provider import ProviderRateLimitError
from backend.application.use_cases.market_data import (
    PROFILE_MAX_AGE_DAYS,
    MarketDataManager,
)
from backend.domain.entities.security import Bar, BarsSyncState, Profile, Quote

NOW = datetime.now(tz=timezone.utc)
TODAY = NOW.date()
YESTERDAY = TODAY - timedelta(days=1)
START = TODAY - timedelta(days=365)


def _bar(symbol: str) -> Bar:
    return Bar(
        symbol=symbol, date=YESTERDAY, open=1, high=2, low=0.5, close=1.5, volume=10
    )


def _quote(symbol: str) -> Quote:
    return Quote(
        symbol=symbol,
        name=symbol,
        exchange="X",
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        currency="USD",
        volume=10,
        change=0.1,
        change_percent=0.01,
        previousClose=1.4,
        timestamp=NOW,
    )


def _profile(symbol: str, age_days: float, aware: bool = True) -> Profile:
    fetched = NOW - timedelta(days=age_days)
    return Profile(
        symbol=symbol, date=fetched if aware else fetched.replace(tzinfo=None)
    )


def _manager(primary: MagicMock, backup: MagicMock | None = None) -> MarketDataManager:
    return MarketDataManager(ds_primary=primary, ds_backup=backup, db=MagicMock())


def _synced(symbol: str) -> BarsSyncState:
    return BarsSyncState(
        symbol=symbol,
        last_bar_date=YESTERDAY - timedelta(days=3),
        last_checked_at=NOW - timedelta(days=1),
        last_success_at=NOW - timedelta(days=1),
        status="ok",
    )


# ── pending_profiles ────────────────────────────────────────────────────────


def test_unforced_refresh_fetches_only_missing_profiles() -> None:
    manager = _manager(MagicMock())
    manager.db.read_profiles.return_value = [_profile("OLD", age_days=400)]

    assert manager.pending_profiles(["OLD", "NEW"]) == ["NEW"]


def test_forced_refresh_skips_recent_profiles() -> None:
    manager = _manager(MagicMock())
    manager.db.read_profiles.return_value = [
        _profile("FRESH", age_days=PROFILE_MAX_AGE_DAYS - 1),
        _profile("STALE", age_days=PROFILE_MAX_AGE_DAYS + 1),
        _profile("NAIVE_STALE", age_days=PROFILE_MAX_AGE_DAYS + 1, aware=False),
    ]

    pending = manager.pending_profiles(
        ["FRESH", "STALE", "NAIVE_STALE", "MISSING"], force=True
    )

    assert pending == ["STALE", "NAIVE_STALE", "MISSING"]


# ── Failed symbols are reported ─────────────────────────────────────────────


def test_refresh_quotes_returns_symbols_without_a_quote() -> None:
    primary = MagicMock()
    primary.fetch_batch_quotes.side_effect = lambda batch: [
        _quote(s) for s in batch if s != "BAD"
    ]
    manager = _manager(primary)

    failed = asyncio.run(manager.refresh_quotes_async(["A", "BAD", "C"]))

    assert failed == ["BAD"]
    assert [q.symbol for q in manager.db.upsert_quotes_batch.call_args[0][0]] == [
        "A",
        "C",
    ]


def test_refresh_quotes_with_nothing_to_do_returns_no_failures() -> None:
    assert asyncio.run(_manager(MagicMock()).refresh_quotes_async([])) == []


def test_refresh_profiles_returns_failed_symbols() -> None:
    primary = MagicMock()

    def fetch(symbol: str) -> Profile:
        if symbol == "BAD":
            raise RuntimeError("no profile")
        return _profile(symbol, age_days=0)

    primary.fetch_stock_profile.side_effect = fetch
    manager = _manager(primary)

    failed = asyncio.run(manager.refresh_profiles_async(["A", "BAD"]))

    assert failed == ["BAD"]


def test_refresh_bars_returns_failed_symbols() -> None:
    primary = MagicMock()

    def fetch(symbol: str, start: date, end: date) -> list[Bar]:
        if symbol == "BAD":
            raise RuntimeError("no data")
        return [_bar(symbol)]

    primary.fetch_bars.side_effect = fetch
    manager = _manager(primary)
    pending = [("A", START, YESTERDAY), ("BAD", START, YESTERDAY)]
    states = {"A": _synced("A"), "BAD": _synced("BAD")}

    failed = asyncio.run(manager.refresh_bars_async(pending, sync_states=states))

    assert failed == ["BAD"]


# ── Rate-limited bars stay unchecked ────────────────────────────────────────


def _written_states(manager: MarketDataManager) -> dict[str, BarsSyncState]:
    if not manager.db.upsert_bars_sync_states.called:
        return {}
    return {s.symbol: s for s in manager.db.upsert_bars_sync_states.call_args[0][0]}


def test_rate_limited_bars_do_not_mark_the_symbol_checked() -> None:
    primary = MagicMock()
    primary.fetch_bars.side_effect = ProviderRateLimitError("still limited")
    manager = _manager(primary)

    failed = asyncio.run(
        manager.refresh_bars_async(
            [("AAA", START, YESTERDAY)],
            sync_states={"AAA": _synced("AAA")},
            trim_before_date=START,
        )
    )

    assert failed == ["AAA"]
    assert _written_states(manager) == {}
    manager.db.trim_bars_batch.assert_not_called()


def test_no_data_failure_still_marks_the_symbol_checked() -> None:
    primary = MagicMock()
    primary.fetch_bars.side_effect = RuntimeError("No bars data")
    manager = _manager(primary)

    asyncio.run(
        manager.refresh_bars_async(
            [("AAA", START, YESTERDAY)], sync_states={"AAA": _synced("AAA")}
        )
    )

    state = _written_states(manager)["AAA"]
    assert state.status == "error"
    assert state.last_checked_at.date() == TODAY


def test_rate_limited_primary_recovered_by_backup_is_a_success() -> None:
    primary = MagicMock()
    primary.fetch_bars.side_effect = ProviderRateLimitError("still limited")
    backup = MagicMock()
    backup.fetch_bars.return_value = [_bar("AAA")]
    manager = _manager(primary, backup)

    failed = asyncio.run(
        manager.refresh_bars_async(
            [("AAA", START, YESTERDAY)], sync_states={"AAA": _synced("AAA")}
        )
    )

    assert failed == []
    assert _written_states(manager)["AAA"].status == "ok"


def test_rate_limited_on_backup_after_primary_error_stays_unchecked() -> None:
    primary = MagicMock()
    primary.fetch_bars.side_effect = RuntimeError("primary down")
    backup = MagicMock()
    backup.fetch_bars.side_effect = ProviderRateLimitError("still limited")
    manager = _manager(primary, backup)

    asyncio.run(
        manager.refresh_bars_async(
            [("AAA", START, YESTERDAY)], sync_states={"AAA": _synced("AAA")}
        )
    )

    assert _written_states(manager) == {}


def test_bars_are_stored_before_the_sync_state_changes() -> None:
    # Readers cache bars by sync-state version, so the version must move last
    primary = MagicMock()
    primary.fetch_bars.return_value = [_bar("AAA")]
    manager = _manager(primary)

    asyncio.run(
        manager.refresh_bars_async(
            [("AAA", START, YESTERDAY)],
            sync_states={"AAA": _synced("AAA")},
            trim_before_date=START,
        )
    )

    writes = [
        call[0]
        for call in manager.db.method_calls
        if call[0] in ("upsert_bars", "trim_bars_batch", "upsert_bars_sync_states")
    ]
    assert writes == ["upsert_bars", "trim_bars_batch", "upsert_bars_sync_states"]
