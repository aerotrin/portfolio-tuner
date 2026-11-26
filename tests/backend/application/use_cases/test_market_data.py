"""Tests for MarketDataManager use cases."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.backend.application.use_cases.market_data import (
    ANALYTICS_LOOKBACK_DAYS,
    MarketDataManager,
)
from src.backend.domain.entities.security import Bar, BarsSyncState, Quote
from tests.backend.conftest import build_global_rates, build_quote

# ---------------------------------------------------------------------------
# Fixed reference dates
# ---------------------------------------------------------------------------
TODAY = datetime.now(tz=timezone.utc).date()
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)
START_DATE = TODAY - timedelta(days=365)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
def _bar(symbol: str, d: date) -> Bar:
    return Bar(
        symbol=symbol, date=d, open=1.0, high=2.0, low=0.5, close=1.5, volume=100_000
    )


class FakeDB:
    def __init__(
        self,
        sync_states: dict[str, BarsSyncState] | None = None,
        first_bar_dates: dict[str, date] | None = None,
    ):
        """first_bar_dates=None means every synced symbol already covers START_DATE."""
        self._states: dict[str, BarsSyncState] = sync_states or {}
        self._first_bar_dates = first_bar_dates
        self.first_bar_calls: list[list[str]] = []
        self.upserted_states: list[BarsSyncState] = []
        self.upserted_bars: list[Bar] = []
        self.trimmed: list[tuple[list[str], date]] = []

    def read_bars_sync_states(self, symbols: list[str]) -> dict[str, BarsSyncState]:
        return {s: self._states.get(s, BarsSyncState(symbol=s)) for s in symbols}

    def read_first_bar_dates(self, symbols: list[str]) -> dict[str, date]:
        self.first_bar_calls.append(list(symbols))
        if self._first_bar_dates is None:
            return {s: START_DATE for s in symbols}
        return {
            s: self._first_bar_dates[s] for s in symbols if s in self._first_bar_dates
        }

    def upsert_bars_sync_states(self, states: list[BarsSyncState]) -> None:
        self.upserted_states.extend(states)

    def upsert_bars(self, bars: list[Bar]) -> None:
        self.upserted_bars.extend(bars)

    def trim_bars_batch(self, symbols: list[str], before_date: date) -> None:
        self.trimmed.append((symbols, before_date))

    def _final_state(self, symbol: str) -> BarsSyncState | None:
        """Return the last upserted state for a symbol."""
        matches = [s for s in self.upserted_states if s.symbol == symbol]
        return matches[-1] if matches else None


class FakePrimary:
    def __init__(
        self,
        bars_by_symbol: dict[str, list[Bar]] | None = None,
        raises: bool = False,
        raises_for: set[str] | None = None,
    ):
        self._bars = bars_by_symbol or {}
        self._raises = raises
        self._raises_for = raises_for or set()
        self.fetch_calls: list[tuple[str, date, date]] = []

    def fetch_bars(self, symbol: str, from_date: date, to_date: date) -> list[Bar]:
        self.fetch_calls.append((symbol, from_date, to_date))
        if self._raises or symbol in self._raises_for:
            raise RuntimeError("fetch error")
        return self._bars.get(symbol, [])


def _manager(db: FakeDB, primary: FakePrimary) -> MarketDataManager:
    return MarketDataManager(ds_primary=primary, ds_backup=MagicMock(), db=db)


# ---------------------------------------------------------------------------
# TestPendingBars — tests the skip/pending classification logic
# ---------------------------------------------------------------------------
class TestPendingBars:
    def test_empty_symbols_returns_empty(self):
        db = FakeDB()
        pending, sync_states = _manager(db, FakePrimary()).pending_bars([])
        assert pending == []
        assert sync_states == {}

    def test_already_checked_today_is_excluded(self):
        """Symbol checked earlier today → excluded from pending list."""
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL",
                    last_checked_at=checked_today,
                    last_bar_date=YESTERDAY,
                    status="ok",
                )
            }
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert pending == []
        assert sync_states == {}

    def test_up_to_date_symbol_is_excluded(self):
        """last_bar_date >= yesterday → excluded from pending list."""
        db = FakeDB(
            {"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=YESTERDAY, status="ok")}
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert pending == []
        assert sync_states == {}

    def test_null_last_bar_date_yields_full_range(self):
        """No prior data → fetch from start_date through yesterday."""
        db = FakeDB(
            {"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=None, status="pending")}
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert len(pending) == 1
        sym, fetch_start, fetch_end = pending[0]
        assert sym == "AAPL"
        assert fetch_start == START_DATE
        assert fetch_end == YESTERDAY
        assert "AAPL" in sync_states

    def test_stale_symbol_yields_incremental_range(self):
        """last_bar_date is stale → fetch from last_bar_date+1 through yesterday."""
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok"
                )
            }
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert len(pending) == 1
        _, fetch_start, fetch_end = pending[0]
        assert fetch_start == TWO_DAYS_AGO + timedelta(days=1)
        assert fetch_end == YESTERDAY

    def test_force_bypasses_sync_state(self):
        """force=True includes a symbol that would otherwise be skipped."""
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL",
                    last_checked_at=checked_today,
                    last_bar_date=YESTERDAY,
                    status="ok",
                )
            }
        )
        pending, _ = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE, force=True
        )
        assert len(pending) == 1
        _, fetch_start, _ = pending[0]
        assert fetch_start == START_DATE

    def test_sync_states_trimmed_to_pending_only(self):
        """Returned sync_states only contains symbols actually in pending."""
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL", last_bar_date=YESTERDAY, status="ok"
                ),  # up-to-date → skipped
                "MSFT": BarsSyncState(
                    symbol="MSFT", last_bar_date=TWO_DAYS_AGO, status="ok"
                ),  # stale → pending
            }
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL", "MSFT"], start_date=START_DATE
        )
        assert len(pending) == 1
        assert pending[0][0] == "MSFT"
        assert "MSFT" in sync_states
        assert "AAPL" not in sync_states

    def test_multiple_symbols_classified_independently(self):
        """Each symbol follows its own classification path."""
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB(
            {
                "CHECKED": BarsSyncState(
                    symbol="CHECKED", last_checked_at=checked_today, status="ok"
                ),
                "UPTODATE": BarsSyncState(
                    symbol="UPTODATE", last_bar_date=YESTERDAY, status="ok"
                ),
                "STALE": BarsSyncState(
                    symbol="STALE", last_bar_date=TWO_DAYS_AGO, status="ok"
                ),
                "NEW": BarsSyncState(
                    symbol="NEW", last_bar_date=None, status="pending"
                ),
            }
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["CHECKED", "UPTODATE", "STALE", "NEW"], start_date=START_DATE
        )
        pending_syms = {p[0] for p in pending}
        assert pending_syms == {"STALE", "NEW"}
        assert set(sync_states.keys()) == {"STALE", "NEW"}


# ---------------------------------------------------------------------------
# TestPendingBarsBackfill — stored history shorter than the window is re-fetched
# ---------------------------------------------------------------------------
class TestPendingBarsBackfill:
    LATE_FIRST_BAR = START_DATE + timedelta(days=11)
    GRACE_FIRST_BAR = START_DATE + timedelta(days=10)

    def test_late_first_bar_yields_full_range(self):
        """Stale symbol whose history starts too late → full window, not incremental."""
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok"
                )
            },
            first_bar_dates={"AAPL": self.LATE_FIRST_BAR},
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert pending == [("AAPL", START_DATE, YESTERDAY)]
        assert "AAPL" in sync_states

    def test_up_to_date_symbol_with_late_first_bar_still_backfills(self):
        """last_bar_date == yesterday does not exempt a short history."""
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL", last_bar_date=YESTERDAY, status="ok"
                )
            },
            first_bar_dates={"AAPL": self.LATE_FIRST_BAR},
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert pending == [("AAPL", START_DATE, YESTERDAY)]
        assert "AAPL" in sync_states

    def test_first_bar_within_grace_is_not_backfilled(self):
        """First bar up to 10 days after the window start → normal classification."""
        db = FakeDB(
            {
                "UPTODATE": BarsSyncState(
                    symbol="UPTODATE", last_bar_date=YESTERDAY, status="ok"
                ),
                "STALE": BarsSyncState(
                    symbol="STALE", last_bar_date=TWO_DAYS_AGO, status="ok"
                ),
            },
            first_bar_dates={
                "UPTODATE": self.GRACE_FIRST_BAR,
                "STALE": self.GRACE_FIRST_BAR,
            },
        )
        pending, _ = _manager(db, FakePrimary()).pending_bars(
            ["UPTODATE", "STALE"], start_date=START_DATE
        )
        assert pending == [("STALE", TWO_DAYS_AGO + timedelta(days=1), YESTERDAY)]

    def test_missing_first_bar_entry_yields_full_range(self):
        """Sync state says bars exist but none are stored → full window."""
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL", last_bar_date=YESTERDAY, status="ok"
                )
            },
            first_bar_dates={},
        )
        pending, _ = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert pending == [("AAPL", START_DATE, YESTERDAY)]

    def test_already_checked_today_is_not_backfilled_or_queried(self):
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL",
                    last_checked_at=checked_today,
                    last_bar_date=YESTERDAY,
                    status="ok",
                )
            },
            first_bar_dates={"AAPL": self.LATE_FIRST_BAR},
        )
        pending, sync_states = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE
        )
        assert pending == []
        assert sync_states == {}
        assert db.first_bar_calls == []

    def test_first_bar_query_skipped_without_candidates(self):
        """Symbols with no bars yet need no first-bar lookup."""
        db = FakeDB(
            {"NEW": BarsSyncState(symbol="NEW", last_bar_date=None, status="pending")}
        )
        pending, _ = _manager(db, FakePrimary()).pending_bars(
            ["NEW"], start_date=START_DATE
        )
        assert pending == [("NEW", START_DATE, YESTERDAY)]
        assert db.first_bar_calls == []

    def test_first_bar_query_limited_to_candidates(self):
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB(
            {
                "CHECKED": BarsSyncState(
                    symbol="CHECKED",
                    last_checked_at=checked_today,
                    last_bar_date=YESTERDAY,
                    status="ok",
                ),
                "NEW": BarsSyncState(
                    symbol="NEW", last_bar_date=None, status="pending"
                ),
                "STALE": BarsSyncState(
                    symbol="STALE", last_bar_date=TWO_DAYS_AGO, status="ok"
                ),
            }
        )
        _manager(db, FakePrimary()).pending_bars(
            ["CHECKED", "NEW", "STALE"], start_date=START_DATE
        )
        assert db.first_bar_calls == [["STALE"]]

    def test_force_yields_full_range_without_first_bar_query(self):
        db = FakeDB(
            {
                "AAPL": BarsSyncState(
                    symbol="AAPL", last_bar_date=YESTERDAY, status="ok"
                )
            },
            first_bar_dates={"AAPL": START_DATE},
        )
        pending, _ = _manager(db, FakePrimary()).pending_bars(
            ["AAPL"], start_date=START_DATE, force=True
        )
        assert pending == [("AAPL", START_DATE, YESTERDAY)]
        assert db.first_bar_calls == []


# ---------------------------------------------------------------------------
# TestRefreshBarsAsync — tests the async fetch/upsert logic directly
# Inputs (pending, sync_states) are constructed explicitly.
# ---------------------------------------------------------------------------
class TestRefreshBarsAsync:
    def test_successful_fetch_upserts_bars_and_updates_state(self):
        """Bars returned → upsert_bars called, state updated with ok + new last_bar_date."""
        bars = [_bar("AAPL", YESTERDAY)]
        db = FakeDB()
        primary = FakePrimary({"AAPL": bars})
        manager = _manager(db, primary)
        pending = [("AAPL", START_DATE, YESTERDAY)]
        sync_states = {
            "AAPL": BarsSyncState(
                symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok"
            )
        }
        asyncio.run(manager.refresh_bars_async(pending, sync_states))

        assert db.upserted_bars == bars
        state = db._final_state("AAPL")
        assert state.status == "ok"
        assert state.last_bar_date == YESTERDAY
        assert state.last_checked_at is not None
        assert state.last_success_at is not None

    def test_empty_bars_result_sets_ok_without_upsert(self):
        """Provider returns no bars (e.g. holiday) → status=ok, no upsert_bars."""
        db = FakeDB()
        primary = FakePrimary({"AAPL": []})
        manager = _manager(db, primary)
        pending = [("AAPL", START_DATE, YESTERDAY)]
        sync_states = {
            "AAPL": BarsSyncState(
                symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok"
            )
        }
        asyncio.run(manager.refresh_bars_async(pending, sync_states))

        assert db.upserted_bars == []
        state = db._final_state("AAPL")
        assert state.status == "ok"
        assert state.last_bar_date == TWO_DAYS_AGO  # unchanged

    def test_fetch_error_sets_error_status_for_previously_valid_symbol(self):
        """Both providers raise for symbol with prior last_success_at → status=error, last_bar_date preserved."""
        last_success = datetime.now(tz=timezone.utc) - timedelta(days=1)
        db = FakeDB()
        primary = FakePrimary(raises=True)
        backup = FakePrimary(raises=True)
        manager = MarketDataManager(ds_primary=primary, ds_backup=backup, db=db)
        pending = [("AAPL", START_DATE, YESTERDAY)]
        sync_states = {
            "AAPL": BarsSyncState(
                symbol="AAPL",
                last_bar_date=TWO_DAYS_AGO,
                last_success_at=last_success,
                status="ok",
            )
        }
        asyncio.run(manager.refresh_bars_async(pending, sync_states))

        assert db.upserted_bars == []
        state = db._final_state("AAPL")
        assert state.status == "error"
        assert state.last_bar_date == TWO_DAYS_AGO  # unchanged

    def test_fetch_error_skips_write_for_never_valid_symbol(self):
        """Both providers raise for symbol with no last_success_at → no DB write."""
        db = FakeDB()
        primary = FakePrimary(raises=True)
        backup = FakePrimary(raises=True)
        manager = MarketDataManager(ds_primary=primary, ds_backup=backup, db=db)
        pending = [("QWERTY", START_DATE, YESTERDAY)]
        sync_states = {
            "QWERTY": BarsSyncState(
                symbol="QWERTY", last_bar_date=None, status="pending"
            )
        }
        asyncio.run(manager.refresh_bars_async(pending, sync_states))

        assert db.upserted_bars == []
        assert db._final_state("QWERTY") is None

    def test_no_trim_when_trim_before_date_is_none(self):
        """trim_bars_batch is not called when trim_before_date is None."""
        db = FakeDB()
        primary = FakePrimary({"AAPL": [_bar("AAPL", YESTERDAY)]})
        manager = _manager(db, primary)
        pending = [("AAPL", START_DATE, YESTERDAY)]
        sync_states = {
            "AAPL": BarsSyncState(
                symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok"
            )
        }
        asyncio.run(
            manager.refresh_bars_async(pending, sync_states, trim_before_date=None)
        )

        assert db.trimmed == []

    def test_trim_only_runs_for_succeeded_symbols(self):
        """trim_bars_batch is called only for symbols that fetched successfully; failed ones are excluded."""
        last_success = datetime.now(tz=timezone.utc) - timedelta(days=1)
        db = FakeDB()
        # AAPL raises on primary; MSFT succeeds
        primary = FakePrimary(
            bars_by_symbol={"MSFT": [_bar("MSFT", YESTERDAY)]},
            raises_for={"AAPL"},
        )
        backup = FakePrimary(raises=True)  # backup also fails for AAPL
        manager = MarketDataManager(ds_primary=primary, ds_backup=backup, db=db)
        pending = [
            ("AAPL", START_DATE, YESTERDAY),
            ("MSFT", START_DATE, YESTERDAY),
        ]
        sync_states = {
            "AAPL": BarsSyncState(
                symbol="AAPL",
                last_bar_date=TWO_DAYS_AGO,
                last_success_at=last_success,
                status="ok",
            ),
            "MSFT": BarsSyncState(
                symbol="MSFT", last_bar_date=TWO_DAYS_AGO, status="ok"
            ),
        }
        asyncio.run(
            manager.refresh_bars_async(
                pending, sync_states, trim_before_date=START_DATE
            )
        )

        assert len(db.trimmed) == 1
        trimmed_symbols, before_date = db.trimmed[0]
        assert set(trimmed_symbols) == {"MSFT"}  # AAPL excluded — fetch failed
        assert before_date == START_DATE

    def test_trim_skips_all_when_all_fail(self):
        """No trim call at all when every fetch fails."""
        db = FakeDB()
        last_success = datetime.now(tz=timezone.utc) - timedelta(days=1)
        primary = FakePrimary(raises=True)
        backup = FakePrimary(raises=True)
        manager = MarketDataManager(ds_primary=primary, ds_backup=backup, db=db)
        pending = [("AAPL", START_DATE, YESTERDAY)]
        sync_states = {
            "AAPL": BarsSyncState(
                symbol="AAPL",
                last_bar_date=TWO_DAYS_AGO,
                last_success_at=last_success,
                status="ok",
            )
        }
        asyncio.run(
            manager.refresh_bars_async(
                pending, sync_states, trim_before_date=START_DATE
            )
        )

        assert db.trimmed == []

    def test_multiple_symbols_processed_independently(self):
        """Each symbol's fetch result is handled independently."""
        db = FakeDB()
        primary = FakePrimary(
            {
                "STALE": [_bar("STALE", YESTERDAY)],
                "NEW": [_bar("NEW", YESTERDAY)],
            }
        )
        manager = _manager(db, primary)
        pending = [
            ("STALE", TWO_DAYS_AGO + timedelta(days=1), YESTERDAY),
            ("NEW", START_DATE, YESTERDAY),
        ]
        sync_states = {
            "STALE": BarsSyncState(
                symbol="STALE", last_bar_date=TWO_DAYS_AGO, status="ok"
            ),
            "NEW": BarsSyncState(symbol="NEW", last_bar_date=None, status="pending"),
        }
        asyncio.run(manager.refresh_bars_async(pending, sync_states))

        assert db._final_state("STALE").status == "ok"
        assert db._final_state("NEW").status == "ok"
        assert len(db.upserted_bars) == 2


# ---------------------------------------------------------------------------
# TestFetchSingleMethods — tests synchronous single-fetch with backup fallback
# ---------------------------------------------------------------------------
class TestFetchSingleMethods:
    def _manager_with(self, primary, backup=None) -> MarketDataManager:
        return MarketDataManager(ds_primary=primary, ds_backup=backup, db=MagicMock())

    # --- fetch_single_quote ---

    def test_fetch_single_quote_returns_primary_result(self):
        primary = MagicMock()
        primary.fetch_quote.return_value = MagicMock(symbol="AAPL")
        result = self._manager_with(primary).fetch_single_quote("AAPL")
        assert result is not None
        assert result.symbol == "AAPL"
        primary.fetch_quote.assert_called_once_with("AAPL")

    def test_fetch_single_quote_falls_back_to_backup_on_primary_failure(self):
        primary = MagicMock()
        primary.fetch_quote.side_effect = RuntimeError("primary down")
        backup = MagicMock()
        backup.fetch_quote.return_value = MagicMock(symbol="AAPL")
        result = self._manager_with(primary, backup).fetch_single_quote("AAPL")
        assert result is not None
        backup.fetch_quote.assert_called_once_with("AAPL")

    def test_fetch_single_quote_returns_none_when_no_backup(self):
        primary = MagicMock()
        primary.fetch_quote.side_effect = RuntimeError("primary down")
        result = self._manager_with(primary, backup=None).fetch_single_quote("AAPL")
        assert result is None

    def test_fetch_single_quote_returns_none_when_both_fail(self):
        primary = MagicMock()
        primary.fetch_quote.side_effect = RuntimeError("primary down")
        backup = MagicMock()
        backup.fetch_quote.side_effect = RuntimeError("backup down")
        result = self._manager_with(primary, backup).fetch_single_quote("AAPL")
        assert result is None

    # --- fetch_single_profile ---

    def test_fetch_single_profile_returns_primary_result(self):
        primary = MagicMock()
        primary.fetch_stock_profile.return_value = MagicMock(symbol="AAPL")
        result = self._manager_with(primary).fetch_single_profile("AAPL")
        assert result is not None
        primary.fetch_stock_profile.assert_called_once_with("AAPL")

    def test_fetch_single_profile_falls_back_to_backup_on_primary_failure(self):
        primary = MagicMock()
        primary.fetch_stock_profile.side_effect = RuntimeError("primary down")
        backup = MagicMock()
        backup.fetch_stock_profile.return_value = MagicMock(symbol="AAPL")
        result = self._manager_with(primary, backup).fetch_single_profile("AAPL")
        assert result is not None
        backup.fetch_stock_profile.assert_called_once_with("AAPL")

    def test_fetch_single_profile_returns_none_when_no_backup(self):
        primary = MagicMock()
        primary.fetch_stock_profile.side_effect = RuntimeError("primary down")
        result = self._manager_with(primary, backup=None).fetch_single_profile("AAPL")
        assert result is None

    def test_fetch_single_profile_returns_none_when_both_fail(self):
        primary = MagicMock()
        primary.fetch_stock_profile.side_effect = RuntimeError("primary down")
        backup = MagicMock()
        backup.fetch_stock_profile.side_effect = RuntimeError("backup down")
        result = self._manager_with(primary, backup).fetch_single_profile("AAPL")
        assert result is None

    # --- fetch_single_bars ---

    def test_fetch_single_bars_returns_primary_result(self):
        bars = [_bar("AAPL", YESTERDAY)]
        primary = FakePrimary({"AAPL": bars})
        result = self._manager_with(primary).fetch_single_bars(
            "AAPL", START_DATE, YESTERDAY
        )
        assert result == bars

    def test_fetch_single_bars_falls_back_to_backup_on_primary_failure(self):
        bars = [_bar("AAPL", YESTERDAY)]
        primary = FakePrimary(raises=True)
        backup = MagicMock()
        backup.fetch_bars.return_value = bars
        result = self._manager_with(primary, backup).fetch_single_bars(
            "AAPL", START_DATE, YESTERDAY
        )
        assert result == bars
        backup.fetch_bars.assert_called_once_with("AAPL", START_DATE, YESTERDAY)

    def test_fetch_single_bars_returns_none_when_no_backup(self):
        primary = FakePrimary(raises=True)
        result = self._manager_with(primary, backup=None).fetch_single_bars("AAPL")
        assert result is None

    def test_fetch_single_bars_returns_none_when_both_fail(self):
        primary = FakePrimary(raises=True)
        backup = MagicMock()
        backup.fetch_bars.side_effect = RuntimeError("backup down")
        result = self._manager_with(primary, backup).fetch_single_bars("AAPL")
        assert result is None


# ---------------------------------------------------------------------------
# TestBuildSecurities — a security needs a quote; daily bars are optional
# ---------------------------------------------------------------------------
class TestBuildSecurities:
    def _manager_with_db(self, quotes, bars_map) -> MarketDataManager:
        db = MagicMock()
        db.read_quotes.return_value = quotes
        db.read_batch_bars.return_value = bars_map
        db.read_profiles.return_value = []
        return MarketDataManager(ds_primary=MagicMock(), ds_backup=None, db=db)

    def test_quote_without_bars_builds_from_quote_only(self):
        """A newly listed security has a quote before its first daily bar."""
        manager = self._manager_with_db(
            quotes=[build_quote("ANT", close=42.0)], bars_map={"ANT": []}
        )

        securities = asyncio.run(
            manager.build_securities_batch_async(["ANT"], rates=build_global_rates())
        )

        sec = securities["ANT"]
        assert len(sec.bars) == 1
        assert sec.bars[0].close == pytest.approx(42.0)
        assert len(sec.indicators) == 1

    def test_batch_defaults_start_date_to_analytics_lookback(self):
        manager = self._manager_with_db(
            quotes=[build_quote("ANT", close=42.0)], bars_map={"ANT": []}
        )

        asyncio.run(
            manager.build_securities_batch_async(["ANT"], rates=build_global_rates())
        )

        manager.db.read_batch_bars.assert_called_once_with(
            ["ANT"], TODAY - timedelta(days=ANALYTICS_LOOKBACK_DAYS), None
        )

    def test_batch_keeps_explicit_start_date(self):
        manager = self._manager_with_db(
            quotes=[build_quote("ANT", close=42.0)], bars_map={"ANT": []}
        )

        asyncio.run(
            manager.build_securities_batch_async(
                ["ANT"], start_date=TWO_DAYS_AGO, rates=build_global_rates()
            )
        )

        manager.db.read_batch_bars.assert_called_once_with(["ANT"], TWO_DAYS_AGO, None)

    def test_single_defaults_start_date_to_analytics_lookback(self):
        db = MagicMock()
        db.read_quote.return_value = build_quote("ANT", close=42.0)
        db.read_bars.return_value = []
        db.read_profile.return_value = None
        manager = MarketDataManager(ds_primary=MagicMock(), ds_backup=None, db=db)

        manager._build_security("ANT", rates=build_global_rates())

        db.read_bars.assert_called_once_with(
            "ANT", TODAY - timedelta(days=ANALYTICS_LOOKBACK_DAYS), None
        )

    def test_single_keeps_explicit_start_date(self):
        db = MagicMock()
        db.read_quote.return_value = build_quote("ANT", close=42.0)
        db.read_bars.return_value = []
        db.read_profile.return_value = None
        manager = MarketDataManager(ds_primary=MagicMock(), ds_backup=None, db=db)

        manager._build_security(
            "ANT", start_date=TWO_DAYS_AGO, rates=build_global_rates()
        )

        db.read_bars.assert_called_once_with("ANT", TWO_DAYS_AGO, None)

    def test_missing_quote_still_raises(self):
        manager = self._manager_with_db(
            quotes=[], bars_map={"ANT": [_bar("ANT", YESTERDAY)]}
        )

        with pytest.raises(ValueError, match="Security data missing for symbol: ANT"):
            asyncio.run(
                manager.build_securities_batch_async(
                    ["ANT"], rates=build_global_rates()
                )
            )


# ── Price chart ─────────────────────────────────────────────────────────────


def _chart_manager(bars: list[Bar], quote: Quote | None) -> MarketDataManager:
    db = MagicMock()
    db.read_bars.return_value = bars
    db.read_quote.return_value = quote
    db.read_profile.return_value = None
    return MarketDataManager(ds_primary=MagicMock(), ds_backup=None, db=db)


def test_price_chart_is_none_for_unknown_symbol() -> None:
    assert _chart_manager([], None).compute_security_price_chart("NOPE") is None


def test_price_chart_reads_full_stored_history() -> None:
    bars = [
        Bar(
            symbol="AAA",
            open=10.0,
            high=11.0,
            low=9.0,
            close=10.0 + i,
            volume=100.0,
            date=date(2024, 1, 1) + timedelta(days=i),
        )
        for i in range(3)
    ]
    manager = _chart_manager(bars, None)

    chart = manager.compute_security_price_chart("AAA", "ema", [2])

    assert chart is not None
    manager.db.read_bars.assert_called_once_with("AAA", None, None)
    assert chart.series.close == [10.0, 11.0, 12.0]
    assert chart.series.moving_averages[0].kind == "ema"
    assert chart.series.moving_averages[0].period == 2
