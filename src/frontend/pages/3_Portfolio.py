import logging

import pandas as pd
import streamlit as st

from frontend.services.streamlit_data import (
    check_missing_symbols,
    load_account_details,
    load_account_records,
    load_accounts_list,
    load_portfolio_snapshot,
    load_security_data,
    load_total_portfolio_snapshot,
)
from frontend.shared.accounts import account_labels, market_priced_symbols
from frontend.shared.dataframe import (
    build_holdings_view,
    build_security_analytics,
    combine_header_data,
)
from frontend.shared.jobs import (
    auto_refresh_if_missing,
    check_job_status,
    maybe_auto_refresh_data,
    render_refresh_job_ui,
    start_refresh_job,
)
from frontend.shared.settings import MASKED_VALUE
from frontend.widgets.allocation import render_portfolio_allocation
from frontend.widgets.correlation import render_correlation_matrix
from frontend.widgets.export_summary import (
    SLOT_KEY as EXPORT_SLOT_KEY,
    render_export_summary_button,
)
from frontend.widgets.kpis import (
    render_account_summary,
    render_market_snapshot,
    render_status_inline,
)
from frontend.widgets.optimizer import render_optimizer
from frontend.widgets.performance import render_performance_view
from frontend.widgets.positions import render_portfolio_positions
from frontend.widgets.reports import (
    render_cash_flows_table,
    render_closed_lots_table,
    render_records_header,
    render_transactions_table,
)

logger = logging.getLogger(__name__)

active_page = "portfolio"
st.session_state["active_page"] = active_page

ALL_ACCOUNTS = "ALL"

# --- Session state -----------------------------------------------------------
try:
    user_id = st.session_state["user_id"]
    hide_balances = st.session_state["hide_balances_toggle"]
    hide_account_numbers = st.session_state["hide_account_numbers_toggle"]

    start_date = st.session_state["start_date"]
    end_date = st.session_state["end_date"]

    header_symbols = st.session_state["header_symbols"]
    benchmark_symbols = st.session_state["benchmark_symbols"]
    base_symbols = st.session_state["base_symbols"]

    benchmark = st.session_state["benchmark"]

    rates = st.session_state["rates"]

except KeyError as exc:
    st.error("App state is not initialized. Please refresh browser.")
    logger.exception("Missing session key on Portfolio page: %s", exc)
    st.stop()
    raise

# --- Account scope -----------------------------------------------------------
# The selector's session value drives the whole page (and the sidebar's active
# account, derived in app.py before this script runs). Sanitize before the
# widget is instantiated so deselection or a deleted account snaps to "ALL".
accounts_list = load_accounts_list(user_id)
scope_labels = account_labels(accounts_list, hide_account_numbers)
number_labels = {a.number: scope_labels[a.id] for a in accounts_list}
number_types = {a.number: a.type for a in accounts_list}

if st.session_state.get("portfolio_account_scope") not in (
    ALL_ACCOUNTS,
    *scope_labels,
):
    st.session_state["portfolio_account_scope"] = ALL_ACCOUNTS
scope = st.session_state["portfolio_account_scope"]
single = scope != ALL_ACCOUNTS
account = load_account_details(scope) if single else None

# -- Header: title + status cluster, then scope selector + refresh ------------
with st.container(
    horizontal=True, vertical_alignment="bottom", horizontal_alignment="distribute"
):
    st.markdown(
        f"#### 📊 {account.type} Portfolio" if single else "#### 🧺 Portfolio",
        width="content",
    )
    # Nested content-width container keeps the status cluster tight on the right
    with st.container(horizontal=True, vertical_alignment="bottom", width="content"):
        render_status_inline(rates, active_page)

with st.container(
    horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"
):
    st.segmented_control(
        "Account scope",
        options=[ALL_ACCOUNTS, *scope_labels],
        format_func=lambda v: "All Accounts" if v == ALL_ACCOUNTS else scope_labels[v],
        key="portfolio_account_scope",
        label_visibility="collapsed",
        width="content",
    )
    # Click handled below, once page_symbols is computed
    refresh_clicked = st.button(
        "Refresh Data",
        icon=":material/refresh:",
        type="secondary",
        key="portfolio_refresh_button",
    )

# --- Auto job status checking ------------------------------------------------
check_job_status()
render_refresh_job_ui(active_page)

# --- Load account records ----------------------------------------------------
# The refresh scope always covers holdings across every account, so switching
# scope (or account) always shows current data.
all_holdings: set[str] = set()
for acc in accounts_list:
    recs = load_account_records(acc.id)
    all_holdings.update(market_priced_symbols(recs.open_positions))

records = load_account_records(scope) if single else None
portfolio_symbols = (
    sorted(market_priced_symbols(records.open_positions))
    if single
    else sorted(all_holdings)
)
page_symbols = sorted(all_holdings | set(base_symbols))
st.session_state["page_symbols"] = page_symbols

# --- Handle Refresh Data click (button rendered in the header row) -----------
if refresh_clicked:
    start_refresh_job(
        symbols=page_symbols,
        blocking=False,
        active_page=active_page,
        start_date=start_date,
        end_date=end_date,
    )

# --- Ensure all page symbols are available else blocking refresh job --------
missing_symbols = sorted(check_missing_symbols(tuple(page_symbols)))
auto_refresh_if_missing(missing_symbols, active_page, start_date, end_date)

# --- Timed / first-visit background refresh (Auto Refresh toggle) ------------
maybe_auto_refresh_data()

# --- Load base data (header + benchmark only) ------------------------------
securities = load_security_data(base_symbols, start_date, end_date)

# --- Load portfolio data (scoped to the selection) ---------------------------
portfolio = (
    load_portfolio_snapshot(scope, start_date, end_date)
    if single
    else load_total_portfolio_snapshot(user_id, start_date, end_date)
)

# --- Sidebar export (slot created by app.py) ---------------------------------
export_slot = st.session_state.get(EXPORT_SLOT_KEY)
if export_slot is not None:
    with export_slot:
        render_export_summary_button(
            portfolio.summary_rows, account.number if account else None
        )

# --- Make header dataframes -------------------------------------------------------
header_quotes = combine_header_data(header_symbols, securities)
st.session_state["last_us_timestamp"] = header_quotes[
    (header_quotes["currency"] == "USD")
]["timestamp"].max()
st.session_state["last_ca_timestamp"] = header_quotes[
    header_quotes["currency"] == "CAD"
]["timestamp"].max()

# Render KPIs --------------------------------------------------------------------
if single:
    render_account_summary(
        scope_labels[scope],
        MASKED_VALUE if hide_account_numbers else account.name,
        portfolio.summary,
        hide_balances,
    )
else:
    render_account_summary(
        "Combined #ALL", "All Accounts", portfolio.summary, hide_balances
    )

# Per-account slices carry the backend's full label and the owner name
account_slices = [
    {
        **s,
        "label": scope_labels.get(s["id"], s["label"]),
        "name": MASKED_VALUE if hide_account_numbers else s["name"],
    }
    for s in portfolio.accounts
]

# --- Market snapshot --------------------------------------------------------------------
render_market_snapshot(header_quotes)

# --- Benchmark dataframes ---------------------------------------------------
benchmark_quotes = combine_header_data([benchmark], securities)
benchmark_analytics = build_security_analytics([benchmark], securities)
benchmark_close_norm = benchmark_analytics.close_norm

new_cols = benchmark_analytics.metrics.columns.difference(benchmark_quotes.columns)
benchmark_data = benchmark_quotes.join(
    benchmark_analytics.metrics[new_cols], how="left"
)


# --- Holdings + portfolio data (only when the scope has positions) ------------
holdings_data = None
performance_data = None
holdings_close_norm = None
portfolio_metrics = None
portfolio_close_norm = None
portfolio_correlation_matrix = None
portfolio_correlation_excluded: list[str] = []
fixed_income_names: list[str] = []

# Tested on holdings, not symbols: a fixed-income-only scope has no market symbols
if portfolio.holdings:
    view = build_holdings_view(portfolio, portfolio_symbols)
    fixed_income_names = view.fixed_income
    holdings_data = view.holdings_data
    performance_data = view.performance_data
    holdings_close_norm = view.close_norm
    portfolio_metrics = view.portfolio_metrics
    portfolio_close_norm = view.portfolio_close_norm
    portfolio_correlation_matrix = view.correlation_matrix
    portfolio_correlation_excluded = view.correlation_excluded
    # All-accounts holdings carry the raw account number — show the label
    if not single and "account" in holdings_data.columns:
        holdings_data["account_type"] = holdings_data["account"].map(
            lambda n: number_types.get(n, n)
        )
        holdings_data["account"] = holdings_data["account"].map(
            lambda n: number_labels.get(n, n)
        )

# --- Account records dataframes (selected account only) -----------------------
transactions = pd.DataFrame()
closed_lots = pd.DataFrame()
cash_flows = pd.DataFrame()
if single:
    transactions = pd.DataFrame.from_records(records.transactions)
    if not transactions.empty:
        transactions["transaction_date"] = pd.to_datetime(
            transactions["transaction_date"], errors="coerce"
        )
        transactions = transactions.sort_values(
            by="transaction_date", ascending=False
        ).reset_index(drop=True)

    closed_lots = pd.DataFrame.from_records(records.closed_lots)
    if not closed_lots.empty:
        closed_lots["close_date"] = pd.to_datetime(
            closed_lots["close_date"], errors="coerce"
        )
        closed_lots = closed_lots.sort_values(by="close_date", ascending=False)

    cash_flows = pd.DataFrame.from_records(records.cash_flows)
    if not cash_flows.empty:
        cash_flows["transaction_date"] = pd.to_datetime(
            cash_flows["transaction_date"], errors="coerce"
        )
        cash_flows = cash_flows.sort_values(by="transaction_date", ascending=False)

# --- Render tabs --------------------------------------------------------------------
tabs = st.tabs(
    [
        "Positions",
        "Performance",
        "Allocation",
        "Correlation",
        "Optimization",
        "Records",
    ]
)

with tabs[0]:
    render_portfolio_positions(
        holdings_data,
        hide_balances,
        cash_accounts=account_slices,
        portfolio_total_value=portfolio.summary.get("total_value") or 0.0,
    )

with tabs[1]:
    render_performance_view(
        metrics=performance_data,
        close_norm_eod=holdings_close_norm,
        benchmark_metrics=benchmark_data,
        benchmark_close_norm_eod=benchmark_close_norm,
        risk_free_rate=rates["rf_rate"],
        key_prefix="holdings" if single else "total",
        portfolio_metrics=portfolio_metrics,
        portfolio_close_norm_eod=portfolio_close_norm,
        use_group_filter=False,
        fixed_income=fixed_income_names,
    )

with tabs[2]:
    render_portfolio_allocation(
        portfolio.summary,
        portfolio.allocation,
        hide_balances,
        context_id=scope if single else "total-portfolio",
        account_labels=number_labels,
    )

with tabs[3]:
    render_correlation_matrix(
        portfolio_correlation_matrix,
        portfolio_correlation_excluded,
        fixed_income=fixed_income_names,
    )

with tabs[4]:
    render_optimizer(
        portfolio_symbols=portfolio_symbols,
        holdings_data=holdings_data,
        portfolio_metrics=portfolio_metrics,
        context_id=scope if single else "total-portfolio",
        context_label=scope_labels[scope] if single else "All Accounts",
        benchmark_data=benchmark_data,
        risk_free_rate=rates["rf_rate"],
        fixed_income=fixed_income_names,
    )

with tabs[5]:
    if single:
        rec_start, rec_end = render_records_header(transactions)
        if rec_start:
            render_closed_lots_table(
                closed_lots, account.tax_status, rec_start, rec_end
            )
            render_cash_flows_table(cash_flows, rec_start, rec_end)
            render_transactions_table(transactions, rec_start, rec_end, scope)
    else:
        st.info("Select an account above to view its records.")
