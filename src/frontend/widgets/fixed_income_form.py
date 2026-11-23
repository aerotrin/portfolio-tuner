from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from frontend.services.streamlit_data import (
    create_fixed_income,
    load_portfolio_snapshot,
    preview_fixed_income,
    record_fixed_income_interest,
    redeem_fixed_income,
)
from frontend.shared.dto import (
    Compounding,
    Currency,
    FixedIncomeCreate,
    FixedIncomeInterest,
    FixedIncomeRedemption,
    FixedIncomeType,
    InstrumentTerms,
    PaymentFrequency,
)
from frontend.shared.fixed_income import (
    CUSTOM_TERM,
    DEFAULT_TERM,
    TERM_PRESETS,
    holding_labels,
    manageable_holdings,
    maturity_for_term,
)

FUND_FROM_CASH = "Account cash"
FUND_BY_DEPOSIT = "New deposit"
NON_REDEEMABLE = "Non-redeemable"
REDEEMABLE = "Redeemable"

MODE_ADD = "Add"
MODE_REDEEM = "Record redemption"
MODE_INTEREST = "Record interest"
MODES = [MODE_ADD, MODE_REDEEM, MODE_INTEREST]

# Holding picker and per-holding inputs, cleared each time the modal opens
_EVENT_STATE_PREFIXES = ("fi_holding", "fi_redeem_", "fi_interest_")


def reset_manage_state(account_id: str) -> None:
    """Open the modal clean: on the given account, on Add, with no inputs
    left over from an earlier holding (whose principal cap may have changed)."""
    stale = [
        key
        for key in st.session_state
        if isinstance(key, str) and key.startswith(_EVENT_STATE_PREFIXES)
    ]
    for key in stale:
        del st.session_state[key]
    st.session_state["fi_account"] = account_id
    st.session_state["fi_mode"] = MODE_ADD


def _event_key(field: str, account_id: str, symbol: str) -> str:
    """Per-holding widget key, so each holding shows its own defaults."""
    return f"fi_{field}::{account_id}::{symbol}"


def _sync_maturity_to_term() -> None:
    maturity = maturity_for_term(
        st.session_state["fi_issue"], st.session_state["fi_term"]
    )
    if maturity is not None:
        st.session_state["fi_maturity"] = maturity


def _mark_term_custom() -> None:
    issue, term = st.session_state["fi_issue"], st.session_state["fi_term"]
    if maturity_for_term(issue, term) != st.session_state["fi_maturity"]:
        st.session_state["fi_term"] = CUSTOM_TERM


def _account_cash(account_id: str) -> float:
    snapshot = load_portfolio_snapshot(
        account_id, st.session_state["start_date"], st.session_state["end_date"]
    )
    return float(snapshot.summary.get("cash_balance", 0.0) or 0.0)


def _render_preview(terms: InstrumentTerms, principal: float, currency: str) -> None:
    preview = preview_fixed_income(terms, principal)
    if preview is None:
        st.caption("Preview unavailable.")
        return
    with st.container(horizontal=True, border=True):
        st.metric("Matures", f"{terms.maturity_date:%b %d, %Y}")
        st.metric(
            f"Interest at maturity ({currency})",
            f"{preview['interest_at_maturity']:,.2f}",
        )
        st.metric(f"Maturity value ({currency})", f"{preview['maturity_value']:,.2f}")
        st.metric(f"Value today ({currency})", f"{preview['value_today']:,.2f}")
    if preview["status"] == "Matured":
        st.caption(
            ":material/event_available: This term has already ended. The holding "
            "will show as matured until its redemption is recorded."
        )


def _render_add_form(account_id: str, fx_rate: float) -> None:
    """Enter a GIC or term deposit from its terms; no market symbol involved."""
    st.session_state.setdefault("fi_issue", date.today())
    st.session_state.setdefault("fi_term", DEFAULT_TERM)
    if "fi_maturity" not in st.session_state:
        if st.session_state["fi_term"] not in TERM_PRESETS:
            st.session_state["fi_term"] = DEFAULT_TERM
        _sync_maturity_to_term()

    c = st.columns([1, 2])
    instrument_type = c[0].segmented_control(
        "Type",
        list(FixedIncomeType),
        default=FixedIncomeType.GIC,
        key="fi_type",
    )
    name = c[1].text_input(
        "Issuer",
        placeholder="e.g. the bank or trust company",
        key="fi_name",
    )

    c = st.columns(3)
    principal = c[0].number_input(
        "Principal", min_value=0.0, step=1000.0, format="%.2f", key="fi_principal"
    )
    rate_pct = c[1].number_input(
        "Annual rate %",
        min_value=0.0,
        max_value=100.0,
        step=0.05,
        format="%.3f",
        key="fi_rate",
    )
    currency = c[2].segmented_control(
        "Currency", list(Currency), default=Currency.CAD, key="fi_currency"
    )

    c = st.columns(3)
    issue_date = c[0].date_input(
        "Issue date",
        max_value="today",
        key="fi_issue",
        on_change=_sync_maturity_to_term,
    )
    c[1].selectbox(
        "Term",
        [*TERM_PRESETS, CUSTOM_TERM],
        key="fi_term",
        on_change=_sync_maturity_to_term,
    )
    maturity_date = c[2].date_input(
        "Maturity date", key="fi_maturity", on_change=_mark_term_custom
    )

    c = st.columns(2)
    frequency = c[0].selectbox(
        "Interest paid", list(PaymentFrequency), key="fi_frequency"
    )
    at_maturity = frequency == PaymentFrequency.AT_MATURITY
    compounding = c[1].selectbox(
        "Interest calculation",
        list(Compounding),
        format_func=lambda v: (
            "Simple" if v == Compounding.SIMPLE else "Compounded annually"
        ),
        key="fi_compounding",
        disabled=not at_maturity,
        help="Compounding applies only when interest is paid at maturity.",
    )
    c = st.columns(2)
    redeemable = c[0].segmented_control(
        "Redeemability",
        [NON_REDEEMABLE, REDEEMABLE],
        default=NON_REDEEMABLE,
        key="fi_redeemable",
    )
    funding = c[1].segmented_control(
        "Paid from",
        [FUND_FROM_CASH, FUND_BY_DEPOSIT],
        default=FUND_FROM_CASH,
        key="fi_funding",
        help=(
            "Account cash: the purchase reduces the account's cash balance. "
            "New deposit: a matching deposit is recorded with the purchase, so "
            "the cash balance is unchanged."
        ),
    )

    currency = currency or Currency.CAD
    ready = principal > 0 and maturity_date > issue_date
    if maturity_date <= issue_date:
        st.warning("The maturity date must be after the issue date.")

    st.divider()
    terms = None
    if ready:
        terms = InstrumentTerms(
            type=instrument_type or FixedIncomeType.GIC,
            name=name.strip(),
            issue_date=issue_date,
            maturity_date=maturity_date,
            annual_rate=rate_pct / 100,
            payment_frequency=frequency,
            compounding=compounding if at_maturity else Compounding.SIMPLE,
            redeemable=redeemable == REDEEMABLE,
        )
        _render_preview(terms, principal, currency)
        if funding != FUND_BY_DEPOSIT:
            cash = _account_cash(account_id)
            cost = principal * (fx_rate if currency == Currency.USD else 1.0)
            if cost > cash:
                st.caption(
                    f":material/warning: This purchase is more than the account's "
                    f"current cash ({cash:,.2f} CAD), which will go negative. "
                    f"Choose **{FUND_BY_DEPOSIT}** if the money came from outside "
                    "the account."
                )
    else:
        st.caption("Enter the principal and dates to see the maturity figures.")

    if not st.button(
        "Add", type="primary", disabled=terms is None, key="fi_add_submit"
    ):
        return
    assert terms is not None

    payload = FixedIncomeCreate(
        terms=terms,
        principal=principal,
        currency=currency,
        fx_rate=fx_rate,
        funded_by_deposit=funding == FUND_BY_DEPOSIT,
    )
    if create_fixed_income(account_id, payload):
        st.cache_data.clear()
        st.rerun()


def _holding_summary(holding: dict[str, Any]) -> None:
    currency = holding.get("currency", "CAD")
    st.markdown(f"**{holding['name']}**")
    with st.container(horizontal=True, border=True):
        st.metric(f"Principal ({currency})", f"{holding['fi_principal']:,.2f}")
        st.metric(
            f"Accrued interest ({currency})", f"{holding['fi_accrued_interest']:,.2f}"
        )
        st.metric("Maturity", str(holding["fi_maturity_date"]))


def _default_event_date(holding: dict[str, Any]) -> date:
    """Maturity date once matured, otherwise today."""
    maturity = pd.to_datetime(holding.get("fi_maturity_date"), errors="coerce")
    today = date.today()
    return today if pd.isna(maturity) else min(today, maturity.date())


def _render_redemption_form(
    account_id: str, holding: dict[str, Any], fx_rate: float
) -> None:
    """Close a fixed-income holding: principal returns to cash with any interest."""
    _holding_summary(holding)
    held = float(holding["fi_principal"])
    currency = holding.get("currency", "CAD")
    symbol = holding["symbol"]

    c = st.columns(3)
    redemption_date = c[0].date_input(
        "Redemption date",
        value=_default_event_date(holding),
        max_value="today",
        key=_event_key("redeem_date", account_id, symbol),
    )
    principal = c[1].number_input(
        f"Principal redeemed ({currency})",
        min_value=0.0,
        max_value=held,
        value=held,
        format="%.2f",
        key=_event_key("redeem_principal", account_id, symbol),
    )
    interest = c[2].number_input(
        f"Interest paid ({currency})",
        min_value=0.0,
        value=round(float(holding["fi_accrued_interest"]), 2),
        format="%.2f",
        key=_event_key("redeem_interest", account_id, symbol),
        help="Defaults to the interest accrued and not yet received.",
    )
    st.caption(
        f"{principal + interest:,.2f} {currency} moves into the account's cash."
        + ("" if principal >= held else " The rest of the principal stays invested.")
    )

    if st.button(
        "Record redemption",
        type="primary",
        disabled=principal <= 0,
        key="fi_redeem_submit",
    ):
        payload = FixedIncomeRedemption(
            symbol=symbol,
            transaction_date=redemption_date,
            principal=principal,
            interest=interest,
            fx_rate=fx_rate,
        )
        if redeem_fixed_income(account_id, payload):
            st.cache_data.clear()
            st.rerun()


def _render_interest_form(
    account_id: str, holding: dict[str, Any], fx_rate: float
) -> None:
    """Record interest received on a holding that pays out before maturity."""
    _holding_summary(holding)
    currency = holding.get("currency", "CAD")
    symbol = holding["symbol"]

    c = st.columns(2)
    payment_date = c[0].date_input(
        "Payment date",
        value=_default_event_date(holding),
        max_value="today",
        key=_event_key("interest_date", account_id, symbol),
    )
    amount = c[1].number_input(
        f"Interest received ({currency})",
        min_value=0.0,
        value=round(float(holding["fi_accrued_interest"]), 2),
        format="%.2f",
        key=_event_key("interest_amount", account_id, symbol),
        help="Defaults to the interest accrued and not yet received.",
    )
    st.caption("The payment goes to the account's cash; the holding stays open.")
    if holding.get("fi_payment_frequency") == PaymentFrequency.AT_MATURITY:
        st.caption(
            ":material/info: This holding pays its interest at maturity. Use "
            f"**{MODE_REDEEM}** when it matures."
        )

    if st.button(
        "Record interest",
        type="primary",
        disabled=amount <= 0,
        key="fi_interest_submit",
    ):
        payload = FixedIncomeInterest(
            symbol=symbol,
            transaction_date=payment_date,
            amount=amount,
            fx_rate=fx_rate,
        )
        if record_fixed_income_interest(account_id, payload):
            st.cache_data.clear()
            st.rerun()


def _pick_holding(account_id: str) -> dict[str, Any] | None:
    """Holding selector over the account's open fixed income with known terms."""
    snapshot = load_portfolio_snapshot(
        account_id, st.session_state["start_date"], st.session_state["end_date"]
    )
    rows, without_terms = manageable_holdings(snapshot.holdings)
    if without_terms:
        st.caption(
            f":material/info: {without_terms} fixed-income holding(s) in this "
            "account have no known terms; record their redemption in the ledger."
        )
    if not rows:
        st.info("This account has no open GIC or term deposit to record against.")
        return None

    labels = holding_labels(rows)
    if st.session_state.get("fi_holding") not in labels:
        st.session_state.pop("fi_holding", None)
    symbol = st.selectbox(
        "Holding",
        list(labels),
        format_func=lambda key: labels.get(key, key),
        key="fi_holding",
    )
    return next(row for row in rows if row["symbol"] == symbol)


@st.dialog("Manage GIC / term deposit", width="medium")
def manage_fixed_income(
    account_options: dict[str, str],
    default_account_id: str,
    fx_rate: float,
) -> None:
    """Add a GIC or term deposit, or record a redemption or interest payment."""
    if st.session_state.get("fi_account") not in account_options:
        st.session_state["fi_account"] = default_account_id
    if st.session_state.get("fi_mode") not in MODES:
        st.session_state["fi_mode"] = MODE_ADD

    account_id = st.selectbox(
        "Account",
        list(account_options),
        format_func=lambda v: account_options.get(v, v),
        key="fi_account",
    )
    mode = st.segmented_control("Action", MODES, key="fi_mode", required=True)

    if mode == MODE_ADD:
        _render_add_form(account_id, fx_rate)
        return
    holding = _pick_holding(account_id)
    if holding is None:
        return
    if mode == MODE_REDEEM:
        _render_redemption_form(account_id, holding, fx_rate)
    else:
        _render_interest_form(account_id, holding, fx_rate)
