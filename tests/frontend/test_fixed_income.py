from datetime import date

import pytest

from frontend.shared.fixed_income import (
    CUSTOM_TERM,
    DEFAULT_TERM,
    TERM_PRESETS,
    holding_labels,
    manageable_holdings,
    maturity_for_term,
)


def _holding(category: str = "Fixed Income", **fields) -> dict:
    return {"name": "Bank GIC", "holding_category": category, **fields}


def test_manageable_holdings_keeps_fixed_income_with_terms_matured_first():
    holdings = {
        "AAA": _holding("Equity"),
        "GIC-LATE": _holding(fi_principal=1_000.0, fi_days_to_maturity=200),
        "GIC-DUE": _holding(fi_principal=2_000.0, fi_days_to_maturity=-5),
        "GIC-SOON": _holding(fi_principal=3_000.0, fi_days_to_maturity=16),
        "FIXED-INCOME": _holding(fi_principal=None),
    }

    rows, without_terms = manageable_holdings(holdings)

    assert [row["symbol"] for row in rows] == ["GIC-DUE", "GIC-SOON", "GIC-LATE"]
    assert without_terms == 1


def test_manageable_holdings_with_no_fixed_income():
    assert manageable_holdings({"AAA": _holding("Equity")}) == ([], 0)


def test_holding_labels_add_the_key_only_to_a_shared_name():
    rows = [
        {"symbol": "GIC-1", "name": "Bank GIC 2.45% Dec 09 2026"},
        {"symbol": "GIC-2", "name": "Bank GIC 2.45% Dec 09 2026"},
        {"symbol": "GIC-3", "name": "Other GIC 3.00% Jun 01 2027"},
    ]

    assert holding_labels(rows) == {
        "GIC-1": "Bank GIC 2.45% Dec 09 2026 · GIC-1",
        "GIC-2": "Bank GIC 2.45% Dec 09 2026 · GIC-2",
        "GIC-3": "Other GIC 3.00% Jun 01 2027",
    }


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("30 days", date(2026, 1, 8)),
        ("90 days", date(2026, 3, 9)),
        ("1 year", date(2026, 12, 9)),
        ("18 months", date(2027, 6, 9)),
        ("5 years", date(2030, 12, 9)),
    ],
)
def test_preset_term_gives_the_maturity_date(term, expected):
    assert maturity_for_term(date(2025, 12, 9), term) == expected


def test_term_ending_in_a_shorter_month_clamps_to_its_last_day():
    assert maturity_for_term(date(2024, 2, 29), "1 year") == date(2025, 2, 28)
    assert maturity_for_term(date(2025, 8, 31), "18 months") == date(2027, 2, 28)


def test_custom_term_has_no_derived_maturity():
    assert maturity_for_term(date(2025, 12, 9), CUSTOM_TERM) is None
    assert DEFAULT_TERM in TERM_PRESETS
