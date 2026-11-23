"""Behaviour of the Manage GIC / term deposit modal, services stubbed out."""

from datetime import date
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import frontend.widgets.fixed_income_form as form

MATURED = "GIC-5.00-20261019"
ACTIVE = "GIC-3.00-20270601"


def _gic(symbol: str, name: str, principal: float, accrued: float, days: int) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "holding_category": "Fixed Income",
        "currency": "CAD",
        "fi_principal": principal,
        "fi_accrued_interest": accrued,
        "fi_maturity_date": "2026-10-19" if days < 0 else "2027-06-01",
        "fi_days_to_maturity": days,
        "fi_payment_frequency": "At Maturity" if days < 0 else "Semi-Annual",
    }


def _holdings() -> dict[str, dict[str, dict]]:
    return {
        "id-a": {
            "AAA": {"symbol": "AAA", "name": "A", "holding_category": "Equity"},
            ACTIVE: _gic(ACTIVE, "Other Bank 3.00% Jun 01 2027", 5_000.0, 75.5, 190),
            MATURED: _gic(
                MATURED, "Example Bank 5.00% Oct 19 2026", 20_000.0, 1_000.0, -35
            ),
        },
        "id-b": {
            "GIC-4.00-20270301": _gic(
                "GIC-4.00-20270301", "Third Bank 4.00% Mar 01 2027", 1_000.0, 12.0, 98
            )
        },
        "id-c": {
            "FIXED-INCOME": {
                "symbol": "FIXED-INCOME",
                "name": "Fixed income (terms unknown)",
                "holding_category": "Fixed Income",
                "fi_principal": None,
            }
        },
    }


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Stub the service layer; submissions are captured and keep the modal open."""
    seen = SimpleNamespace(holdings=_holdings(), created=[], redeemed=[], interest=[])

    def snapshot(account_id, *_dates):
        return SimpleNamespace(
            summary={"cash_balance": 500.0}, holdings=seen.holdings[account_id]
        )

    def preview(terms, principal):
        interest = principal * terms.annual_rate
        return {
            "interest_at_maturity": interest,
            "maturity_value": principal + interest,
            "value_today": principal,
            "status": "Active",
        }

    def capture(bucket):
        def submit(account_id, payload):
            bucket.append((account_id, payload.model_dump(mode="json")))
            return False

        return submit

    monkeypatch.setattr(form, "load_portfolio_snapshot", snapshot)
    monkeypatch.setattr(form, "preview_fixed_income", preview)
    monkeypatch.setattr(form, "create_fixed_income", capture(seen.created))
    monkeypatch.setattr(form, "redeem_fixed_income", capture(seen.redeemed))
    monkeypatch.setattr(form, "record_fixed_income_interest", capture(seen.interest))
    return seen


def _app() -> None:
    from datetime import date

    import streamlit as st

    import frontend.widgets.fixed_income_form as form

    st.session_state.setdefault("start_date", date(2025, 1, 1))
    st.session_state.setdefault("end_date", date(2026, 11, 23))
    # The sidebar resets the modal's state each time its button opens it
    if st.session_state.pop("reopen", False) or "opened" not in st.session_state:
        form.reset_manage_state("id-a")
        st.session_state["opened"] = True
    form.manage_fixed_income(
        {"id-a": "RRSP #1", "id-b": "TFSA #2", "id-c": "Cash #3"}, "id-a", 1.35
    )


def _open() -> AppTest:
    at = AppTest.from_function(_app, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _switch_mode(at: AppTest, mode: str) -> None:
    at.segmented_control(key="fi_mode").set_value(mode)
    at.run()
    assert not at.exception


def _field(field: str, account_id: str, symbol: str) -> str:
    return f"fi_{field}::{account_id}::{symbol}"


def test_modal_opens_on_add_and_submits_the_terms(calls):
    at = _open()
    assert at.segmented_control(key="fi_mode").value == form.MODE_ADD
    assert at.selectbox(key="fi_account").value == "id-a"

    at.number_input(key="fi_principal").set_value(26_104.02)
    at.number_input(key="fi_rate").set_value(2.45)
    at.date_input(key="fi_issue").set_value(date(2025, 12, 9))
    at.run()
    assert not at.exception
    assert at.date_input(key="fi_maturity").value == date(2026, 12, 9)
    assert [m.label for m in at.metric][0] == "Matures"

    at.button(key="fi_add_submit").click()
    at.run()

    ((account_id, payload),) = calls.created
    assert account_id == "id-a"
    assert payload["principal"] == pytest.approx(26_104.02)
    assert payload["funded_by_deposit"] is False
    assert payload["terms"]["issue_date"] == "2025-12-09"
    assert payload["terms"]["maturity_date"] == "2026-12-09"
    assert payload["terms"]["annual_rate"] == pytest.approx(0.0245)


def test_redemption_defaults_to_the_matured_holding_in_full(calls):
    at = _open()
    _switch_mode(at, form.MODE_REDEEM)

    assert at.selectbox(key="fi_holding").options[0].startswith("Example Bank")
    assert at.selectbox(key="fi_holding").value == MATURED
    principal = at.number_input(key=_field("redeem_principal", "id-a", MATURED))
    interest = at.number_input(key=_field("redeem_interest", "id-a", MATURED))
    assert principal.value == pytest.approx(20_000.0)
    assert interest.value == pytest.approx(1_000.0)
    # A matured holding is redeemed as of its maturity date
    redeemed_on = at.date_input(key=_field("redeem_date", "id-a", MATURED))
    assert redeemed_on.value == date(2026, 10, 19)


def test_switching_to_a_smaller_holding_shows_its_own_figures(calls):
    at = _open()
    _switch_mode(at, form.MODE_REDEEM)

    at.selectbox(key="fi_holding").set_value(ACTIVE)
    at.run()

    assert not at.exception
    principal = at.number_input(key=_field("redeem_principal", "id-a", ACTIVE))
    assert principal.value == pytest.approx(5_000.0)
    assert principal.max == pytest.approx(5_000.0)


def test_switching_account_lists_only_that_accounts_holdings(calls):
    at = _open()
    _switch_mode(at, form.MODE_REDEEM)

    at.selectbox(key="fi_account").set_value("id-b")
    at.run()

    assert not at.exception
    assert at.selectbox(key="fi_holding").value == "GIC-4.00-20270301"
    assert len(at.selectbox(key="fi_holding").options) == 1


def test_account_without_known_terms_explains_instead_of_offering_a_form(calls):
    at = _open()
    _switch_mode(at, form.MODE_INTEREST)

    at.selectbox(key="fi_account").set_value("id-c")
    at.run()

    assert not at.exception
    assert "no open GIC or term deposit" in at.info[0].value
    assert any("no known terms" in c.value for c in at.caption)
    assert not [s for s in at.selectbox if s.key == "fi_holding"]


def test_redemption_and_interest_submit_for_the_selected_holding(calls):
    at = _open()
    _switch_mode(at, form.MODE_REDEEM)
    at.button(key="fi_redeem_submit").click()
    at.run()

    ((account_id, payload),) = calls.redeemed
    assert account_id == "id-a"
    assert payload["symbol"] == MATURED
    assert payload["principal"] == pytest.approx(20_000.0)
    assert payload["interest"] == pytest.approx(1_000.0)
    assert payload["transaction_date"] == "2026-10-19"

    _switch_mode(at, form.MODE_INTEREST)
    at.selectbox(key="fi_holding").set_value(ACTIVE)
    at.run()
    at.number_input(key=_field("interest_amount", "id-a", ACTIVE)).set_value(75.0)
    at.run()
    at.button(key="fi_interest_submit").click()
    at.run()

    ((account_id, payload),) = calls.interest
    assert account_id == "id-a"
    assert payload["symbol"] == ACTIVE
    assert payload["amount"] == pytest.approx(75.0)


def test_reopening_after_a_partial_redemption_starts_from_the_new_principal(calls):
    at = _open()
    _switch_mode(at, form.MODE_REDEEM)
    at.selectbox(key="fi_account").set_value("id-b")
    at.run()

    # Part of the holding has since been redeemed, so its cap is lower
    calls.holdings["id-a"][MATURED]["fi_principal"] = 8_000.0
    at.session_state["reopen"] = True
    at.run()

    assert not at.exception
    assert at.segmented_control(key="fi_mode").value == form.MODE_ADD
    assert at.selectbox(key="fi_account").value == "id-a"

    _switch_mode(at, form.MODE_REDEEM)
    principal = at.number_input(key=_field("redeem_principal", "id-a", MATURED))
    assert principal.value == pytest.approx(8_000.0)
