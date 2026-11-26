from datetime import date
from typing import Optional, Protocol

from backend.domain.entities.security import Bar, Profile, Quote, GlobalRates


class ProviderRateLimitError(Exception):
    """The provider is still refusing requests after the adapter's retries.

    The failure is transient: the data may exist, so callers should not
    record the symbol as checked.
    """


class MarketDataProvider(Protocol):
    def fetch_global_rates(self) -> GlobalRates: ...
    def fetch_quote(self, symbol: str) -> Quote: ...
    def fetch_batch_quotes(self, symbols: list[str]) -> list[Quote]: ...
    def fetch_bars(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> list[Bar]: ...
    def fetch_stock_profile(self, symbol: str) -> Profile: ...
