"""In-process cache of daily bars, so unchanged history is not re-read from the database."""

from dataclasses import dataclass
from datetime import date, datetime
import threading
from typing import Optional

from backend.domain.entities.security import Bar

# (date, open, high, low, close, volume). Plain tuples: a year of bars for
# every symbol is about 100,000 rows, and Bar objects cost over 1 KB each.
BarRow = tuple[date, float, float, float, float, float]
# (last_bar_date, last_success_at) from bars_sync_state; both change whenever
# a refresh writes bars for the symbol
BarsVersion = tuple[Optional[date], Optional[datetime]]


@dataclass
class _Entry:
    version: BarsVersion
    covers_from: Optional[date]  # None: every stored bar of the symbol
    rows: list[BarRow]


def _covers(entry_from: Optional[date], start: Optional[date]) -> bool:
    return entry_from is None or (start is not None and entry_from <= start)


class BarsCache:
    """Bars per symbol, valid while the symbol's sync-state version is unchanged.

    Thread-safe: repository reads run in worker threads.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def get(
        self,
        symbol: str,
        version: BarsVersion,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> Optional[list[Bar]]:
        """Bars in [start, end], or None when the symbol must be read again."""
        with self._lock:
            entry = self._entries.get(symbol)
        if (
            entry is None
            or entry.version != version
            or not _covers(entry.covers_from, start)
        ):
            return None
        return to_bars(symbol, entry.rows, start, end)

    def put(
        self,
        symbol: str,
        version: BarsVersion,
        covers_from: Optional[date],
        rows: list[BarRow],
    ) -> None:
        with self._lock:
            current = self._entries.get(symbol)
            # Keep a wider entry of the same version over a narrower read
            if (
                current is not None
                and current.version == version
                and _covers(current.covers_from, covers_from)
            ):
                return
            self._entries[symbol] = _Entry(version, covers_from, rows)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def to_bars(
    symbol: str,
    rows: list[BarRow],
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> list[Bar]:
    """Rows (already date-ordered) within [start, end] as Bar entities."""
    return [
        Bar.model_construct(
            symbol=symbol, date=d, open=o, high=h, low=lo, close=c, volume=v
        )
        for d, o, h, lo, c, v in rows
        if (start is None or d >= start) and (end is None or d <= end)
    ]


DEFAULT_BARS_CACHE = BarsCache()
