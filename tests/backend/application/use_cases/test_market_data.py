"""Tests for MarketDataManager.refresh_batch_bars_async smart sync logic."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.backend.application.use_cases.market_data import MarketDataManager
from src.backend.domain.entities.security import Bar, BarsSyncState

# ---------------------------------------------------------------------------
# Fixed reference dates
# ---------------------------------------------------------------------------
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)
START_DATE = TODAY - timedelta(days=365)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
def _bar(symbol: str, d: date) -> Bar:
    return Bar(symbol=symbol, date=d, open=1.0, high=2.0, low=0.5, close=1.5, volume=100_000)


class FakeDB:
    def __init__(self, sync_states: dict[str, BarsSyncState] | None = None):
        self._states: dict[str, BarsSyncState] = sync_states or {}
        self.upserted_states: list[BarsSyncState] = []
        self.upserted_bars: list[Bar] = []
        self.trimmed: list[tuple[list[str], date]] = []

    def read_bars_sync_states(self, symbols: list[str]) -> dict[str, BarsSyncState]:
        return {s: self._states.get(s, BarsSyncState(symbol=s)) for s in symbols}

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
    ):
        self._bars = bars_by_symbol or {}
        self._raises = raises
        self.fetch_calls: list[tuple[str, date, date]] = []

    def fetch_bars(self, symbol: str, from_date: date, to_date: date) -> list[Bar]:
        self.fetch_calls.append((symbol, from_date, to_date))
        if self._raises:
            raise RuntimeError("FMP error")
        return self._bars.get(symbol, [])


def _manager(db: FakeDB, primary: FakePrimary) -> MarketDataManager:
    return MarketDataManager(ds_primary=primary, ds_backup=MagicMock(), db=db)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestRefreshBatchBarsAsync:

    def test_already_checked_today_is_skipped_entirely(self):
        """Symbol checked earlier today → no fetch, no state write."""
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_checked_at=checked_today, last_bar_date=YESTERDAY, status="ok")})
        primary = FakePrimary()
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert primary.fetch_calls == []
        assert db.upserted_states == []

    def test_up_to_date_symbol_is_skipped_with_state_write(self):
        """last_bar_date >= yesterday → status=skipped, last_checked_at stamped, no fetch."""
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=YESTERDAY, status="ok")})
        primary = FakePrimary()
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert primary.fetch_calls == []
        state = db._final_state("AAPL")
        assert state is not None
        assert state.status == "skipped"
        assert state.last_checked_at is not None
        assert state.last_bar_date == YESTERDAY

    def test_null_last_bar_date_fetches_full_range(self):
        """No prior data → fetch from start_date through yesterday."""
        bars = [_bar("AAPL", YESTERDAY)]
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=None, status="pending")})
        primary = FakePrimary({"AAPL": bars})
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert len(primary.fetch_calls) == 1
        sym, fetch_start, fetch_end = primary.fetch_calls[0]
        assert sym == "AAPL"
        assert fetch_start == START_DATE
        assert fetch_end == YESTERDAY

    def test_stale_data_fetches_incremental_range(self):
        """last_bar_date is stale → fetch from last_bar_date+1 through yesterday."""
        bars = [_bar("AAPL", YESTERDAY)]
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok")})
        primary = FakePrimary({"AAPL": bars})
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert len(primary.fetch_calls) == 1
        _, fetch_start, fetch_end = primary.fetch_calls[0]
        assert fetch_start == TWO_DAYS_AGO + timedelta(days=1)  # = YESTERDAY
        assert fetch_end == YESTERDAY

    def test_successful_fetch_upserts_bars_and_updates_state(self):
        """Bars returned → upsert_bars called, state updated with ok + new last_bar_date."""
        bars = [_bar("AAPL", YESTERDAY)]
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok")})
        primary = FakePrimary({"AAPL": bars})
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert db.upserted_bars == bars
        state = db._final_state("AAPL")
        assert state.status == "ok"
        assert state.last_bar_date == YESTERDAY
        assert state.last_checked_at is not None
        assert state.last_success_at is not None

    def test_empty_bars_result_sets_ok_without_upsert(self):
        """Provider returns no bars (e.g. holiday) → status=ok, no upsert_bars."""
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok")})
        primary = FakePrimary({"AAPL": []})
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert db.upserted_bars == []
        state = db._final_state("AAPL")
        assert state.status == "ok"
        assert state.last_bar_date == TWO_DAYS_AGO  # unchanged

    def test_fetch_error_sets_error_status(self):
        """Provider raises → status=error, last_bar_date preserved."""
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_bar_date=TWO_DAYS_AGO, status="ok")})
        primary = FakePrimary(raises=True)
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE))

        assert db.upserted_bars == []
        state = db._final_state("AAPL")
        assert state.status == "error"
        assert state.last_bar_date == TWO_DAYS_AGO  # unchanged

    def test_force_bypasses_sync_state_and_fetches_full_range(self):
        """force=True ignores last_checked_at and last_bar_date, fetches full range."""
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB({"AAPL": BarsSyncState(symbol="AAPL", last_checked_at=checked_today, last_bar_date=YESTERDAY, status="ok")})
        primary = FakePrimary({"AAPL": [_bar("AAPL", YESTERDAY)]})
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"], start_date=START_DATE, force=True))

        assert len(primary.fetch_calls) == 1
        _, fetch_start, fetch_end = primary.fetch_calls[0]
        assert fetch_start == START_DATE
        assert fetch_end == YESTERDAY

    def test_trim_called_for_all_symbols_when_start_date_provided(self):
        """trim_bars_batch is called with all symbols and start_date regardless of sync outcome."""
        db = FakeDB({
            "AAPL": BarsSyncState(symbol="AAPL", last_bar_date=YESTERDAY, status="ok"),  # skipped
            "MSFT": BarsSyncState(symbol="MSFT", last_bar_date=TWO_DAYS_AGO, status="ok"),  # pending
        })
        primary = FakePrimary({"MSFT": [_bar("MSFT", YESTERDAY)]})
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(
            ["AAPL", "MSFT"], start_date=START_DATE
        ))

        assert len(db.trimmed) == 1
        trimmed_symbols, before_date = db.trimmed[0]
        assert set(trimmed_symbols) == {"AAPL", "MSFT"}
        assert before_date == START_DATE

    def test_no_trim_when_start_date_is_none(self):
        """trim_bars_batch is not called when no start_date provided."""
        db = FakeDB()
        primary = FakePrimary()
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(["AAPL"]))

        assert db.trimmed == []

    def test_multiple_symbols_independent_classification(self):
        """Each symbol follows its own sync path independently."""
        checked_today = datetime.now(tz=timezone.utc)
        db = FakeDB({
            "ALREADY": BarsSyncState(symbol="ALREADY", last_checked_at=checked_today, status="ok"),
            "UPTODATE": BarsSyncState(symbol="UPTODATE", last_bar_date=YESTERDAY, status="ok"),
            "STALE": BarsSyncState(symbol="STALE", last_bar_date=TWO_DAYS_AGO, status="ok"),
            "NEW": BarsSyncState(symbol="NEW", last_bar_date=None, status="pending"),
        })
        primary = FakePrimary({
            "STALE": [_bar("STALE", YESTERDAY)],
            "NEW": [_bar("NEW", YESTERDAY)],
        })
        asyncio.run(_manager(db, primary).refresh_batch_bars_async(
            ["ALREADY", "UPTODATE", "STALE", "NEW"], start_date=START_DATE
        ))

        fetched_symbols = {c[0] for c in primary.fetch_calls}
        assert fetched_symbols == {"STALE", "NEW"}
        assert db._final_state("ALREADY") is None   # no write
        assert db._final_state("UPTODATE").status == "skipped"
        assert db._final_state("STALE").status == "ok"
        assert db._final_state("NEW").status == "ok"
