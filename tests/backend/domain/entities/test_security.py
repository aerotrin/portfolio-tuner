from datetime import datetime
import math

from src.backend.domain.entities.security import Quote, finite_or_zero


def _make_quote(**overrides: object) -> Quote:
    payload: dict[str, object] = {
        "symbol": "TEST",
        "name": "Test Inc.",
        "exchange": "TEST",
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "currency": "USD",
        "volume": 1_000,
        "change": 0.5,
        "change_percent": 0.05,
        "previousClose": 10.0,
        "timestamp": datetime(2024, 1, 1, 16, 0, 0),
    }
    payload.update(overrides)
    return Quote(**payload)  # type: ignore[arg-type]


def test_finite_or_zero_replaces_missing_and_non_finite():
    assert finite_or_zero(None) == 0.0
    assert finite_or_zero(float("nan")) == 0.0
    assert finite_or_zero(float("inf")) == 0.0
    assert finite_or_zero(float("-inf")) == 0.0
    assert finite_or_zero(1.5) == 1.5
    assert finite_or_zero(0) == 0


def test_quote_coerces_nan_fields_to_zero():
    quote = _make_quote(change=float("nan"), change_percent=float("nan"))
    assert quote.change == 0.0
    assert quote.change_percent == 0.0


def test_quote_coerces_none_fields_to_zero():
    quote = _make_quote(open=None, volume=None, previousClose=None)
    assert quote.open == 0.0
    assert quote.volume == 0.0
    assert quote.previousClose == 0.0


def test_quote_json_has_no_nulls_for_numeric_fields():
    """NaN would serialize to JSON null and break frontend arithmetic."""
    quote = _make_quote(close=float("nan"), change=float("nan"))
    dumped = quote.model_dump(mode="json")
    assert not any(v is None for v in dumped.values())
    assert all(math.isfinite(v) for v in dumped.values() if isinstance(v, (int, float)))
