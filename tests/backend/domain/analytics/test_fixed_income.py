from datetime import date

import pytest

from src.backend.domain.analytics.fixed_income import (
    accrual_factor,
    accrual_index,
    accrued_interest,
    accrued_value,
    days_to_maturity,
    instrument_key,
    instrument_status,
    interest_earned,
    maturity_value,
    new_instrument_symbol,
    parse_ledger_terms,
    year_fraction,
)
from src.backend.domain.entities.fixed_income import (
    Compounding,
    FixedIncomeStatus,
    InstrumentTerms,
    PaymentFrequency,
)

LEDGER_BUY = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon         5.00  FLEXIBLE GIC               AM NON-TRANSFERABLE DUE "
    "11/07/2024 05.000% SECURITIES OF A RELATED ISSUER UNSOLICITED "
    ">:CY-655410655 R#7204953"
)
LEDGER_INTEREST = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon 5.0000  Maturity NOV 07 2024 Coupon 5.0000 FLEXIBLE GIC               "
    "AM DUE 11/07/2024  INT  5.000% CPN INT   ON   20000 BND REC 11/06/24 PAY "
    "11/07/24"
)
LEDGER_REDEEMED = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon 5.0000  FLEXIBLE GIC               AM DUE 11/07/2024  INT  5.000% "
    "ISSUE REDEEMED FOR CASH"
)


def _one_year_gic() -> InstrumentTerms:
    return InstrumentTerms(
        issue_date=date(2025, 12, 9),
        maturity_date=date(2026, 12, 9),
        annual_rate=0.0245,
    )


def test_worked_example_one_year_gic_paid_at_maturity():
    terms = _one_year_gic()
    principal = 26_104.02

    assert interest_earned(principal, terms, terms.maturity_date) == pytest.approx(
        639.55, abs=0.005
    )
    assert maturity_value(principal, terms) == pytest.approx(26_743.57, abs=0.005)

    # The issuer reported 26,717.29 on this date: 350 days, today included
    as_of = date(2026, 11, 23)
    assert (as_of - terms.issue_date).days == 349
    assert accrued_interest(principal, terms, as_of) == pytest.approx(613.27, abs=0.005)
    assert accrued_value(principal, terms, as_of) == pytest.approx(26_717.29, abs=0.005)


def test_the_valuation_date_counts_as_an_earned_day():
    terms = _one_year_gic()
    daily = 0.0245 / 365

    assert accrual_factor(terms, date(2025, 12, 8)) == 1.0
    assert accrual_factor(terms, terms.issue_date) == pytest.approx(1 + daily)
    # The last day's interest is in by the day before maturity
    assert accrual_factor(terms, date(2026, 12, 8)) == pytest.approx(1.0245)


def test_one_year_term_across_a_leap_day_earns_exactly_the_coupon():
    # 366 calendar days, yet the issuer paid exactly 5% of 20,000
    terms = InstrumentTerms(
        issue_date=date(2023, 11, 7),
        maturity_date=date(2024, 11, 7),
        annual_rate=0.05,
    )
    assert (terms.maturity_date - terms.issue_date).days == 366
    assert year_fraction(terms.issue_date, terms.maturity_date) == 1.0
    assert interest_earned(20_000, terms, terms.maturity_date) == pytest.approx(1_000.0)


def test_no_accrual_before_issue_or_after_maturity():
    terms = _one_year_gic()
    assert accrual_factor(terms, date(2025, 1, 1)) == 1.0
    assert accrual_factor(terms, date(2030, 1, 1)) == pytest.approx(1.0245)
    assert accrued_value(1_000, terms, date(2030, 1, 1)) == pytest.approx(1_024.5)


def test_annual_compounding_over_a_multi_year_term():
    terms = InstrumentTerms(
        issue_date=date(2024, 1, 15),
        maturity_date=date(2027, 1, 15),
        annual_rate=0.04,
        compounding=Compounding.ANNUAL,
    )
    assert maturity_value(10_000, terms) == pytest.approx(10_000 * 1.04**3)

    simple = terms.model_copy(update={"compounding": Compounding.SIMPLE})
    assert maturity_value(10_000, simple) == pytest.approx(11_200.0)

    # Mid-year: two whole years compounded, then simple on the part-year
    mid = date(2026, 7, 15)
    days = (mid - date(2026, 1, 15)).days + 1
    assert accrual_factor(terms, mid) == pytest.approx(
        1.04**2 * (1 + 0.04 * days / 365)
    )


def test_interest_already_paid_out_is_not_counted_twice():
    terms = InstrumentTerms(
        issue_date=date(2025, 1, 1),
        maturity_date=date(2027, 1, 1),
        annual_rate=0.06,
        payment_frequency=PaymentFrequency.SEMI_ANNUAL,
    )
    as_of = date(2025, 12, 31)
    assert interest_earned(10_000, terms, as_of) == pytest.approx(600.0)
    assert accrued_interest(10_000, terms, as_of, interest_received=300.0) == (
        pytest.approx(300.0)
    )
    assert accrued_value(10_000, terms, as_of, interest_received=600.0) == (
        pytest.approx(10_000.0)
    )
    # Never below principal, even if more was recorded than earned
    assert accrued_value(10_000, terms, as_of, interest_received=900.0) == 10_000


def test_status_and_days_to_maturity():
    terms = _one_year_gic()
    assert instrument_status(terms, date(2026, 12, 8)) == FixedIncomeStatus.ACTIVE
    assert instrument_status(terms, date(2026, 12, 9)) == FixedIncomeStatus.MATURED
    assert days_to_maturity(terms, date(2026, 11, 23)) == 16
    assert days_to_maturity(terms, date(2026, 12, 19)) == -10


def test_accrual_index_follows_the_dates_given():
    terms = _one_year_gic()
    index = accrual_index(
        terms, [date(2025, 12, 1), date(2025, 12, 8), date(2026, 12, 9)]
    )
    assert index.tolist() == pytest.approx([1.0, 1.0, 1.0245])


@pytest.mark.parametrize("description", [LEDGER_BUY, LEDGER_INTEREST, LEDGER_REDEEMED])
def test_every_ledger_row_of_one_gic_resolves_to_the_same_key(description):
    terms = parse_ledger_terms(description, date(2024, 11, 7))
    assert terms is not None
    assert terms.maturity_date == date(2024, 11, 7)
    assert terms.annual_rate == pytest.approx(0.05)
    assert terms.name == "CIBC FLEXIBLE GIC"
    assert instrument_key(terms) == "GIC-5.00-20241107"


def test_ledger_buy_takes_its_settlement_date_as_the_issue_date():
    terms = parse_ledger_terms(LEDGER_BUY, date(2023, 11, 7))
    assert terms is not None
    assert terms.issue_date == date(2023, 11, 7)


def test_description_without_terms_is_not_an_instrument():
    assert parse_ledger_terms("ISHARES INDIA INDEX ETF  UNSOLICITED", None) is None
    assert parse_ledger_terms("", None) is None


def test_manual_symbol_extends_the_key_and_is_unique():
    terms = _one_year_gic()
    first, second = new_instrument_symbol(terms), new_instrument_symbol(terms)
    assert first.startswith("GIC-2.45-20261209-")
    assert first != second


def test_terms_validation():
    with pytest.raises(ValueError):
        InstrumentTerms(
            issue_date=date(2026, 1, 1),
            maturity_date=date(2026, 1, 1),
            annual_rate=0.03,
        )
    with pytest.raises(ValueError):
        InstrumentTerms(
            issue_date=date(2025, 1, 1),
            maturity_date=date(2028, 1, 1),
            annual_rate=0.03,
            payment_frequency=PaymentFrequency.ANNUAL,
            compounding=Compounding.ANNUAL,
        )
