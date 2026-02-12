from dataclasses import dataclass
from typing import Optional, Sequence

import streamlit as st

from frontend.services.streamlit_data import (
    create_account,
    get_account_details,
    patch_account,
)
from frontend.shared.dto import (
    AccountCreateRequest,
    AccountPatchRequest,
    Currency,
    TaxStatus,
)


@dataclass
class AccountFormValues:
    owner: str
    type: str
    currency: Currency
    tax_status: TaxStatus
    benchmark: str


def _account_form(
    benchmark_symbols: Sequence[str],
    defaults: Optional[AccountFormValues] = None,
    key_prefix: str = "account_form",
) -> tuple[AccountFormValues, bool]:
    """Render the form and return (values, submitted)."""
    if not benchmark_symbols:
        st.warning("No benchmark symbols are configured yet.")
        st.stop()

    d = defaults or AccountFormValues(
        owner="",
        type="",
        currency=Currency.CAD,
        tax_status=TaxStatus.NON_REGISTERED,
        benchmark=benchmark_symbols[0],
    )

    with st.form(f"{key_prefix}_form", clear_on_submit=False, border=False):
        owner = st.text_input("Owner", value=d.owner, key=f"{key_prefix}_owner")
        account_type = st.text_input("Type", value=d.type, key=f"{key_prefix}_type")

        currency = st.radio(
            "Currency",
            Currency,
            horizontal=True,
            index=list(Currency).index(d.currency),
            key=f"{key_prefix}_currency",
        )
        status = st.radio(
            "Tax Status",
            TaxStatus,
            horizontal=True,
            index=list(TaxStatus).index(d.tax_status),
            key=f"{key_prefix}_status",
        )
        benchmark = st.selectbox(
            "Benchmark",
            list(benchmark_symbols),
            index=list(benchmark_symbols).index(d.benchmark)
            if d.benchmark in benchmark_symbols
            else 0,
            key=f"{key_prefix}_benchmark",
        )

        submitted = st.form_submit_button("Save", type="primary")

    return AccountFormValues(
        owner, account_type, currency, status, benchmark
    ), submitted


@st.dialog("Create Account", width="small")
def create_account_dialog(benchmark_symbols: Sequence[str]) -> None:
    st.subheader("Create Account")

    number_raw = st.text_input("Number", key="create_number")
    values, submitted = _account_form(
        benchmark_symbols, defaults=None, key_prefix="create"
    )

    if not submitted:
        return

    number = number_raw.strip()
    if not number:
        st.toast("Account number is required.", icon="⚠️")
        return
    if not number.isdigit():
        st.toast("Account number must contain digits only.", icon="⚠️")
        return

    owner = values.owner.strip()
    if not owner:
        st.toast("Owner is required.", icon="⚠️")
        return

    account_type = values.type.strip()
    if not account_type:
        st.toast("Type is required.", icon="⚠️")
        return

    payload = AccountCreateRequest(
        number=number,
        owner=owner,
        type=account_type,
        currency=values.currency,
        tax_status=values.tax_status,
        benchmark=values.benchmark,
    )

    if create_account(payload):
        st.cache_data.clear()
        st.session_state["show_create_account_dialog"] = False
        st.rerun()


@st.dialog("Modify Account", width="small")
def edit_account_dialog(
    account_id: str, account_number: str, benchmark_symbols: Sequence[str]
) -> None:
    st.subheader(f"Modify Account #{account_number}")

    acct = get_account_details(account_id)
    if not acct:
        st.error("Account not found. Please refresh and try again.")
        return

    defaults = AccountFormValues(
        owner=acct.owner or "",
        type=acct.type or "",
        currency=acct.currency or Currency.CAD,
        tax_status=acct.tax_status or TaxStatus.NON_REGISTERED,
        benchmark=acct.benchmark or benchmark_symbols[0],
    )

    values, submitted = _account_form(
        benchmark_symbols,
        defaults=defaults,
        key_prefix=f"edit_{account_id}",
    )

    if not submitted:
        return

    # Build PATCH payload with only changed fields
    patch = AccountPatchRequest()

    new_owner, old_owner = values.owner.strip(), defaults.owner.strip()
    if new_owner != old_owner:
        patch.owner = new_owner

    new_type, old_type = values.type.strip(), defaults.type.strip()
    if new_type != old_type:
        patch.type = new_type

    if values.currency != defaults.currency:
        patch.currency = values.currency

    if values.tax_status != defaults.tax_status:
        patch.tax_status = values.tax_status

    if values.benchmark != defaults.benchmark:
        patch.benchmark = values.benchmark

    # ---- short-circuit empty patch attempt ----
    if patch.model_dump(mode="json", exclude_none=True) == {}:
        st.toast("No changes to save.", icon="ℹ️")
        return

    if patch_account(account_id, patch):
        st.cache_data.clear()
        st.session_state["show_edit_account_dialog"] = False
        st.rerun()
