import pytest

from backend.infra.adapters import rate_limiter as rl
from backend.infra.adapters.rate_limiter import RateLimiter, RateLimiterConfig


class FakeClock:
    """Stands in for time.monotonic / time.sleep so tests never wait."""

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


def test_slots_within_the_window_are_granted_without_waiting(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=3))

    for _ in range(3):
        limiter.acquire_slot()

    assert clock.sleeps == []


def test_full_window_waits_until_the_oldest_slot_expires(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=2))
    limiter.acquire_slot()
    clock.now += 10
    limiter.acquire_slot()

    limiter.acquire_slot()

    assert sum(clock.sleeps) == pytest.approx(50.05)


def test_min_interval_spaces_slots_evenly(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=600, min_interval_sec=0.1))

    for _ in range(4):
        limiter.acquire_slot()

    assert clock.sleeps == pytest.approx([0.1, 0.1, 0.1])


def test_min_interval_does_not_wait_when_enough_time_has_passed(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=600, min_interval_sec=0.1))
    limiter.acquire_slot()
    clock.now += 5

    limiter.acquire_slot()

    assert clock.sleeps == []


def test_cost_consumes_several_slots(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=3))

    limiter.acquire_slot(cost=3)
    limiter.acquire_slot()

    assert sum(clock.sleeps) == pytest.approx(60.05)


def test_backoff_blocks_the_next_slot(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=100))

    limiter.handle_rate_limit(retry_after=15, attempt=1)
    limiter.acquire_slot()

    assert sum(clock.sleeps) == pytest.approx(30)


@pytest.mark.parametrize(
    ("attempt", "expected"), [(1, 30), (2, 60), (3, 120), (4, 120)]
)
def test_backoff_grows_with_attempts_up_to_a_cap(clock, attempt, expected) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=100))

    limiter.handle_rate_limit(retry_after=15, attempt=attempt)
    limiter.acquire_slot()

    assert sum(clock.sleeps) == pytest.approx(expected)


def test_a_shorter_backoff_never_shortens_an_active_one(clock) -> None:
    limiter = RateLimiter(RateLimiterConfig(max_per_minute=100))

    limiter.handle_rate_limit(retry_after=15, attempt=3)
    limiter.handle_rate_limit(retry_after=15, attempt=1)
    limiter.acquire_slot()

    assert sum(clock.sleeps) == pytest.approx(120)
