from datetime import date, datetime, timezone
import threading

from backend.infra.db.bars_cache import BarsCache, to_bars
from backend.infra.db.repo import PgMarketDataRepository

V1 = (date(2026, 11, 25), datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc))
V2 = (date(2026, 11, 26), datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc))
D = [date(2026, 11, d) for d in (20, 23, 24, 25)]


def _rows(days: list[date] = D) -> list[tuple]:
    return [(d, 1.0, 2.0, 0.5, 1.5 + i, 100.0) for i, d in enumerate(days)]


# ── BarsCache ───────────────────────────────────────────────────────────────


def test_miss_when_nothing_is_cached() -> None:
    assert BarsCache().get("AAA", V1) is None


def test_hit_returns_bars_in_date_order() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, None, _rows())

    bars = cache.get("AAA", V1)

    assert [b.date for b in bars] == D
    assert bars[0].symbol == "AAA"
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close) == (1, 2, 0.5, 1.5)
    assert bars[0].volume == 100.0


def test_changed_version_is_a_miss() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, None, _rows())

    assert cache.get("AAA", V2) is None


def test_range_is_filtered_inclusively() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, None, _rows())

    bars = cache.get("AAA", V1, start=D[1], end=D[2])

    assert [b.date for b in bars] == [D[1], D[2]]


def test_entry_from_a_start_date_covers_later_starts_only() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, D[1], _rows(D[1:]))

    assert [b.date for b in cache.get("AAA", V1, start=D[2])] == D[2:]
    assert cache.get("AAA", V1, start=D[0]) is None
    # A request for all stored bars needs an entry that holds all of them
    assert cache.get("AAA", V1) is None


def test_full_entry_covers_any_start() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, None, _rows())

    assert [b.date for b in cache.get("AAA", V1, start=D[3])] == [D[3]]


def test_narrower_read_does_not_replace_a_wider_entry() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, None, _rows())

    cache.put("AAA", V1, D[2], _rows(D[2:]))

    assert len(cache.get("AAA", V1)) == 4


def test_wider_read_and_new_version_replace_the_entry() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, D[2], _rows(D[2:]))

    cache.put("AAA", V1, None, _rows())
    assert len(cache.get("AAA", V1)) == 4

    cache.put("AAA", V2, D[3], _rows(D[3:]))
    assert cache.get("AAA", V1) is None
    assert len(cache.get("AAA", V2, start=D[3])) == 1


def test_symbols_are_independent_and_clear_empties_the_cache() -> None:
    cache = BarsCache()
    cache.put("AAA", V1, None, _rows())

    assert cache.get("BBB", V1) is None
    cache.clear()
    assert cache.get("AAA", V1) is None


def test_concurrent_reads_and_writes_do_not_fail() -> None:
    cache = BarsCache()
    errors: list[Exception] = []

    def work(n: int) -> None:
        try:
            for i in range(200):
                cache.put(f"S{(n + i) % 5}", V1, None, _rows())
                cache.get(f"S{i % 5}", V1)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


# ── Repository reads through the cache ──────────────────────────────────────


class FakeBarsRepo(PgMarketDataRepository):
    """Repository with the two database queries replaced by in-memory data."""

    def __init__(self, cache: BarsCache | None) -> None:
        super().__init__(session=None, bars_cache=cache)
        self.stored: dict[str, list[tuple]] = {"AAA": _rows(), "BBB": _rows(D[2:])}
        self.versions: dict[str, tuple] = {"AAA": V1, "BBB": V1}
        self.fetches: list[tuple[list[str], date | None]] = []

    def _fetch_bar_rows(self, symbols, start_date):
        self.fetches.append((list(symbols), start_date))
        return {
            s: [
                r
                for r in self.stored.get(s, [])
                if not start_date or r[0] >= start_date
            ]
            for s in symbols
        }

    def _read_bar_versions(self, symbols):
        return {s: self.versions.get(s, (None, None)) for s in symbols}


def test_second_read_of_unchanged_symbols_does_not_query_bars() -> None:
    repo = FakeBarsRepo(BarsCache())

    first = repo.read_batch_bars(["AAA", "BBB"], D[1])
    second = repo.read_batch_bars(["AAA", "BBB"], D[1])

    assert repo.fetches == [(["AAA", "BBB"], D[1])]
    assert second == first
    assert [b.date for b in second["AAA"]] == D[1:]


def test_only_symbols_with_a_new_version_are_read_again() -> None:
    repo = FakeBarsRepo(BarsCache())
    repo.read_batch_bars(["AAA", "BBB"], D[0])
    repo.versions["BBB"] = V2
    repo.stored["BBB"] = _rows(D[1:])

    result = repo.read_batch_bars(["AAA", "BBB"], D[0])

    assert repo.fetches[-1] == (["BBB"], D[0])
    assert [b.date for b in result["BBB"]] == D[1:]


def test_cached_result_equals_an_uncached_read() -> None:
    cached, plain = FakeBarsRepo(BarsCache()), FakeBarsRepo(None)
    for start, end in [(D[1], None), (D[1], D[2]), (D[2], D[3]), (None, None)]:
        cached.read_batch_bars(["AAA", "BBB"], start, end)  # warm, then read
        assert cached.read_batch_bars(["AAA", "BBB"], start, end) == (
            plain.read_batch_bars(["AAA", "BBB"], start, end)
        )


def test_end_date_does_not_narrow_what_is_cached() -> None:
    repo = FakeBarsRepo(BarsCache())

    early = repo.read_batch_bars(["AAA"], D[0], D[1])
    later = repo.read_batch_bars(["AAA"], D[0], D[3])

    assert [b.date for b in early["AAA"]] == D[:2]
    assert [b.date for b in later["AAA"]] == D
    assert len(repo.fetches) == 1


def test_earlier_start_than_cached_reads_again_and_widens_the_entry() -> None:
    repo = FakeBarsRepo(BarsCache())
    repo.read_batch_bars(["AAA"], D[2])

    repo.read_batch_bars(["AAA"], D[0])
    repo.read_batch_bars(["AAA"], D[2])

    assert repo.fetches == [(["AAA"], D[2]), (["AAA"], D[0])]


def test_full_history_read_is_cached_and_serves_windowed_reads() -> None:
    repo = FakeBarsRepo(BarsCache())

    assert [b.date for b in repo.read_bars("AAA")] == D
    assert [b.date for b in repo.read_bars("AAA", D[2])] == D[2:]
    assert len(repo.fetches) == 1


def test_unknown_symbol_returns_no_bars_and_keeps_request_order() -> None:
    repo = FakeBarsRepo(BarsCache())

    result = repo.read_batch_bars(["ZZZ", "AAA"], D[0])

    assert list(result) == ["ZZZ", "AAA"]
    assert result["ZZZ"] == []
    assert repo.read_batch_bars([], D[0]) == {}


def test_to_bars_filters_the_range() -> None:
    assert [b.date for b in to_bars("AAA", _rows(), D[1], D[2])] == [D[1], D[2]]
