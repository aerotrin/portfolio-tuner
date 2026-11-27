from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from backend.application.ports.market_data_provider import ProviderRateLimitError
from backend.infra.adapters import rate_limiter as rl
from backend.infra.adapters import yfinance_client as yfc
from backend.infra.adapters.rate_limiter import RateLimiterConfig
from backend.infra.adapters.yfinance_client import (
    PROFILE_REQUESTS,
    QUOTE_REQUESTS,
    YFinanceClient,
    YFinanceConfig,
    paced_limiter_config,
)

MARKET_TIME = 1795640400


class FakeTicker:
    """yf.Ticker stand-in. `failures[symbol]` rate-limits that many calls."""

    failures: dict[str, int] = {}
    info_payload: dict = {}
    info_reads: list[str] = []
    history_calls: list[tuple[str, dict]] = []

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def _maybe_rate_limit(self) -> None:
        if FakeTicker.failures.get(self.symbol, 0) > 0:
            FakeTicker.failures[self.symbol] -= 1
            raise YFRateLimitError()

    @property
    def fast_info(self) -> SimpleNamespace:
        self._maybe_rate_limit()
        return SimpleNamespace(
            regular_market_previous_close=100.0,
            last_price=110.0,
            open=101.0,
            day_high=111.0,
            day_low=99.0,
            last_volume=5000.0,
            exchange="PCX",
            currency="USD",
        )

    def get_history_metadata(self) -> dict:
        return {
            "longName": f"{self.symbol} long name",
            "shortName": f"{self.symbol} short",
            "regularMarketTime": MARKET_TIME,
        }

    @property
    def info(self) -> dict:
        FakeTicker.info_reads.append(self.symbol)
        self._maybe_rate_limit()
        return {
            "quoteType": "ETF",
            "longName": "Fund",
            "marketCap": 5.0e9,
        } | FakeTicker.info_payload

    def history(self, **kwargs) -> pd.DataFrame:
        FakeTicker.history_calls.append((self.symbol, kwargs))
        self._maybe_rate_limit()
        idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
        return pd.DataFrame(
            {"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [0.5, 1.5]}
            | {"Close": [1.5, 2.5], "Volume": [10.0, 20.0]},
            index=idx,
        )


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(rl.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(rl.time, "sleep", fake.sleep)
    return fake


@pytest.fixture(autouse=True)
def fake_yahoo(monkeypatch):
    FakeTicker.failures = {}
    FakeTicker.info_payload = {}
    FakeTicker.info_reads = []
    FakeTicker.history_calls = []
    monkeypatch.setattr(yfc.yf, "Ticker", FakeTicker)


def _client(max_per_minute: int = 10_000, max_retries: int = 3) -> YFinanceClient:
    return YFinanceClient(
        YFinanceConfig(
            rate_limiter=RateLimiterConfig(max_per_minute=max_per_minute),
            max_retries=max_retries,
        )
    )


def test_paced_config_spreads_the_budget_evenly() -> None:
    cfg = paced_limiter_config(600)

    assert cfg.max_per_minute == 600
    assert cfg.min_interval_sec == pytest.approx(0.1)


# ── Quote ───────────────────────────────────────────────────────────────────


def test_quote_is_built_from_price_history_without_reading_info(clock) -> None:
    quote = _client().fetch_quote("SPY")

    assert FakeTicker.info_reads == []
    assert quote.name == "SPY long name"
    assert quote.close == 110.0
    assert quote.previousClose == 100.0
    assert quote.change == pytest.approx(10.0)
    assert quote.change_percent == pytest.approx(0.1)
    assert quote.exchange == "PCX"
    assert quote.timestamp == datetime.fromtimestamp(MARKET_TIME, tz=timezone.utc)


def test_quote_falls_back_to_the_short_name(clock, monkeypatch) -> None:
    monkeypatch.setattr(
        FakeTicker, "get_history_metadata", lambda self: {"shortName": "Short"}
    )

    quote = _client().fetch_quote("SPY")

    assert quote.name == "Short"
    assert quote.timestamp.tzinfo is not None


def test_quote_takes_two_slots(clock) -> None:
    client = _client(max_per_minute=QUOTE_REQUESTS)

    client.fetch_quote("SPY")
    assert clock.sleeps == []
    client.fetch_quote("QQQ")

    assert sum(clock.sleeps) == pytest.approx(60.05)


# ── Retry and backoff ───────────────────────────────────────────────────────


def test_rate_limited_call_backs_off_and_then_succeeds(clock) -> None:
    FakeTicker.failures = {"SPY": 2}

    quote = _client().fetch_quote("SPY")

    assert quote.close == 110.0
    # 15 s base: 30 s after the first refusal, 60 s after the second
    assert sum(clock.sleeps) == pytest.approx(90)


def test_persistent_rate_limit_raises_the_port_error(clock) -> None:
    FakeTicker.failures = {"SPY": 99}

    with pytest.raises(ProviderRateLimitError):
        _client(max_retries=2).fetch_quote("SPY")

    assert FakeTicker.failures["SPY"] == 96


def test_backoff_is_shared_with_other_calls(clock) -> None:
    client = _client()
    FakeTicker.failures = {"SPY": 99}
    with pytest.raises(ProviderRateLimitError):
        client.fetch_quote("SPY")
    clock.sleeps.clear()

    # The last refusal's backoff has not been waited out yet
    client._rate_limiter.handle_rate_limit(15, 1)
    client.fetch_quote("QQQ")

    assert sum(clock.sleeps) == pytest.approx(30)


def test_batch_quotes_skip_a_failed_symbol_and_continue(clock) -> None:
    FakeTicker.failures = {"BAD": 99}

    quotes = _client(max_retries=0).fetch_batch_quotes(["SPY", "BAD", "QQQ"])

    assert [q.symbol for q in quotes] == ["SPY", "QQQ"]


# ── Bars and profile ────────────────────────────────────────────────────────


def test_bars_are_fetched_for_the_requested_window(clock) -> None:
    bars = _client().fetch_bars("SPY", date(2024, 1, 1), date(2024, 1, 3))

    assert [(b.date, b.close) for b in bars] == [
        (date(2024, 1, 2), 1.5),
        (date(2024, 1, 3), 2.5),
    ]
    symbol, kwargs = FakeTicker.history_calls[0]
    assert symbol == "SPY"
    # Yahoo's end date is exclusive
    assert kwargs == {"start": date(2024, 1, 1), "end": date(2024, 1, 4)}


def test_rate_limited_bars_are_retried(clock) -> None:
    FakeTicker.failures = {"SPY": 1}

    bars = _client().fetch_bars("SPY", date(2024, 1, 1), date(2024, 1, 3))

    assert len(bars) == 2
    assert len(FakeTicker.history_calls) == 2


def test_bars_rate_limited_past_retries_raise_the_port_error(clock) -> None:
    FakeTicker.failures = {"SPY": 99}

    with pytest.raises(ProviderRateLimitError):
        _client(max_retries=1).fetch_bars("SPY", date(2024, 1, 1), date(2024, 1, 3))


def test_profile_takes_three_slots(clock) -> None:
    client = _client(max_per_minute=PROFILE_REQUESTS)

    profile = client.fetch_stock_profile("SPY")
    assert profile.marketCap == 5.0e9
    assert clock.sleeps == []
    client.fetch_stock_profile("QQQ")

    assert sum(clock.sleeps) == pytest.approx(60.05)


def test_stock_profile_carries_the_fundamental_inputs(clock) -> None:
    FakeTicker.info_payload = {
        "quoteType": "EQUITY",
        "trailingEps": 8.98,
        "forwardEps": 10.57,
        "dividendRate": 1.08,
        "sharesOutstanding": 5.0e9,
        "impliedSharesOutstanding": 1.2e10,
    }

    profile = _client().fetch_stock_profile("GOOGL")

    assert profile.epsTrailing == 8.98
    assert profile.epsForward == 10.57
    assert profile.dividendRate == 1.08
    # All share classes, not only the listed one
    assert profile.sharesOutstanding == 1.2e10
    assert profile.netAssets is None


def test_fund_profile_recovers_the_dividend_rate_from_the_yield(clock) -> None:
    FakeTicker.info_payload = {
        "quoteType": "ETF",
        "epsTrailingTwelveMonths": 2.87,
        "yield": 0.02,
        "regularMarketPrice": 50.0,
        "sharesOutstanding": 3.5e8,
        "netAssets": 2.3e10,
    }

    profile = _client().fetch_stock_profile("XIU.TO")

    assert profile.epsTrailing == 2.87
    assert profile.epsForward is None
    assert profile.dividendRate == pytest.approx(1.0)
    assert profile.sharesOutstanding is None
    assert profile.netAssets == 2.3e10


def test_profile_drops_non_finite_fundamentals(clock) -> None:
    FakeTicker.info_payload = {
        "quoteType": "EQUITY",
        "trailingEps": float("nan"),
        "epsTrailingTwelveMonths": 4.0,
        "dividendRate": float("inf"),
        "impliedSharesOutstanding": None,
    }

    profile = _client().fetch_stock_profile("AAA")

    assert profile.epsTrailing == 4.0
    assert profile.dividendRate is None
    assert profile.sharesOutstanding is None
