import logging

import pandas as pd
import streamlit as st

from src.presentation.widgets.kpis import (
    render_account_summary,
    render_market_snapshot,
    render_status_strip,
)
from src.presentation.widgets.performance import (
    render_correlation_matrix,
    render_holdings_allocation,
    render_holdings_intraday,
    render_holdings_performance,
    render_positions,
)
from src.presentation.widgets.reports import (
    render_cash_flows_table,
    render_closed_lots_table,
    render_reports_header,
    render_transactions_table,
)
from src.presentation.widgets.transaction_form import transaction_form
from src.services.streamlit_data import (
    load_account_records,
    load_account_summary,
    load_portfolio_data_eod,
    load_portfolio_data_intraday,
    load_security_data_eod,
    load_security_data_intraday,
)
from src.utils.dataframe import (
    add_sparkline,
    combine_header_data,
    make_scalar_wide_df,
    make_timeseries_long_df,
    make_timeseries_wide_df,
    normalize_trends,
)
from src.utils.jobs import check_job_status, render_refresh_job_ui, start_refresh_job

logger = logging.getLogger(__name__)

active_page = "portfolio"

# --- Session state -----------------------------------------------------------
try:
    account_number = st.session_state["account_number"]
    account_name = st.session_state["account_name"]
    account_type = st.session_state["account_type"]

    hide_balances = st.session_state["hide_balances_toggle"]
    start_date = st.session_state["start_date"]
    end_date = st.session_state["end_date"]

    header_symbols = st.session_state["header_symbols"]
    benchmark_symbols = st.session_state["benchmark_symbols"]
    benchmark = st.session_state["benchmark"]

    available_symbols = st.session_state["available_symbols"]
    rates = st.session_state["rates"]

except KeyError as exc:
    st.error("App state is not initialized. Please refresh browser.")
    logger.exception("Missing session key on Holdings page: %s", exc)
    st.stop()


# -- Render header ------------------------------------------------------------
h = st.columns([6, 1], vertical_alignment="center")
with h[0]:
    st.markdown(f"## 📊 {account_type} Portfolio")

# --- Account summary and symbols (selected account) --------------------------------------
account_summary = load_account_summary(account_number, account_name)
st.session_state["account_summary"] = account_summary
account_symbols = account_summary["open_positions"]

# --- Page symbols -----------------------------------------------------------
page_symbols = sorted(
    set(header_symbols) | set(benchmark_symbols) | set(account_symbols)
)

with h[1]:
    holdings_refresh = st.button(
        "Refresh Data",
        icon=":material/refresh:",
        type="secondary",
        key="holdings_refresh_button",
        width="stretch",
    )
    if holdings_refresh:
        start_refresh_job(
            symbols=page_symbols,
            blocking=True,
            intraday=True,
            active_page=active_page,
        )

# --- Auto job status checking ------------------------------------------------
check_job_status()
render_refresh_job_ui(active_page)

# --- Ensure all page symbols are available else blocking refresh job ----------------------------------------
missing_symbols = sorted(set(page_symbols) - set(available_symbols))
if missing_symbols:
    start_refresh_job(
        symbols=missing_symbols, blocking=True, intraday=False, active_page=active_page
    )

# --- Load portfolio data ---------------------------------------------------
portfolio_intraday = load_portfolio_data_intraday(account_number, account_name)
st.session_state["portfolio_summary"] = portfolio_intraday.summary

# --- Load securities data ---------------------------------------------------
securities_intraday = load_security_data_intraday(page_symbols)
securities_eod = load_security_data_eod(page_symbols, start_date, end_date)

# --- Make header dataframes -------------------------------------------------------
header_quotes = combine_header_data(header_symbols, securities_intraday, securities_eod)
st.session_state["last_us_timestamp"] = header_quotes[
    (header_quotes["currency"] == "USD") & (header_quotes["exchange"] == "INDEX")
]["timestamp"].max()  # FTRK-306
st.session_state["last_ca_timestamp"] = header_quotes[
    header_quotes["currency"] == "CAD"
]["timestamp"].max()

# Render KPIs --------------------------------------------------------------------
render_status_strip(rates)

if not hide_balances:
    render_account_summary()

# --- Market snapshot --------------------------------------------------------------------
render_market_snapshot(header_quotes)

# --- Benchmark dataframes ---------------------------------------------------
# Benchmark quotes
benchmark_quotes = combine_header_data([benchmark], securities_intraday, securities_eod)

# Benchmark metrics
benchmark_metrics = make_scalar_wide_df(
    {s: securities_eod.metrics[s] for s in [benchmark]}
)
benchmark_profiles = make_scalar_wide_df(
    {s: securities_eod.profile[s] for s in [benchmark]}
)

# Benchmark bars & indicators
benchmark_bars = make_timeseries_long_df(
    {s: securities_eod.bars[s] for s in [benchmark]}
)
benchmark_indicators = make_timeseries_long_df(
    {s: securities_eod.indicators[s] for s in [benchmark]}
)

# Benchmark closes & close norms
benchmark_closes = make_timeseries_wide_df(benchmark_indicators, "close")
benchmark_close_norm = make_timeseries_wide_df(benchmark_indicators, "close_norm")

# Add sparklines
benchmark_quotes = add_sparkline(
    benchmark_quotes, benchmark_closes, add_intraday_close=True
)
benchmark_metrics = add_sparkline(benchmark_metrics, benchmark_closes)

# --- Load account_number records ---------------------------------------------------
records = load_account_records(account_number, account_name)
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

# --- Holdings + portfolio data (only when account has positions) -------------
holdings_quotes_positions = None
holdings_metrics = None
holdings_close_norm = None
portfolio_metrics = None
portfolio_close_norm = None
portfolio_correlation_matrix = None

if account_symbols:
    portfolio_eod = load_portfolio_data_eod(account_number, account_name)

    # Holdings dataframes
    holdings_quotes_positions = make_scalar_wide_df(portfolio_intraday.holdings)
    holdings_quotes_positions["symbol"] = holdings_quotes_positions.index

    holdings_metrics = make_scalar_wide_df(
        {s: securities_eod.metrics[s] for s in account_symbols}
    )
    holdings_profiles = make_scalar_wide_df(
        {s: securities_eod.profile[s] for s in account_symbols}
    )
    holdings_metrics = normalize_trends(holdings_metrics)

    holdings_bars = make_timeseries_long_df(
        {s: securities_eod.bars[s] for s in account_symbols}
    )
    holdings_indicators = make_timeseries_long_df(
        {s: securities_eod.indicators[s] for s in account_symbols}
    )
    holdings_closes = make_timeseries_wide_df(holdings_indicators, "close")
    holdings_close_norm = make_timeseries_wide_df(holdings_indicators, "close_norm")

    prof_df = holdings_profiles.loc[
        :, ~holdings_profiles.columns.isin(holdings_quotes_positions.columns)
    ]
    holdings_quotes_positions = holdings_quotes_positions.join(prof_df, how="left")

    holdings_quotes_positions = add_sparkline(
        holdings_quotes_positions, holdings_closes, add_intraday_close=True
    )
    holdings_metrics = add_sparkline(holdings_metrics, holdings_closes)

    # Portfolio dataframes
    portfolio_metrics = make_scalar_wide_df(portfolio_eod.metrics)
    portfolio_metrics = portfolio_metrics.set_index("symbol", drop=False)

    portfolio_indicators = make_timeseries_long_df(portfolio_eod.indicators)
    portfolio_closes = make_timeseries_wide_df(portfolio_indicators, "close")
    portfolio_close_norm = make_timeseries_wide_df(portfolio_indicators, "close_norm")

    portfolio_correlation_matrix = pd.DataFrame(
        portfolio_eod.correlation_matrix["entries"]
    )
    portfolio_correlation_matrix = portfolio_correlation_matrix.pivot(
        index="row", columns="col", values="value"
    )

    portfolio_metrics = add_sparkline(portfolio_metrics, portfolio_closes)


# --- Tabs (Reports first; Positions and Performance use prebuilt holdings data when present)
tabs = st.tabs(["Positions", "Performance", "Reports"])

with tabs[2]:
    if not transactions.empty:
        start_date, end_date = render_reports_header(transactions)
        render_closed_lots_table(closed_lots, start_date, end_date)
        render_cash_flows_table(cash_flows, start_date, end_date)
        render_transactions_table(transactions, start_date, end_date)
    else:
        st.info("No transactions found.")


with tabs[0]:
    render_holdings_intraday(holdings_quotes_positions)

    st.divider()

    render_positions(holdings_quotes_positions)

    record_transaction = st.button(
        "Record Transaction", icon=":material/edit:", type="secondary"
    )
    if record_transaction:
        transaction_form(
            account_number,
            account_name,
            holdings_quotes_positions,
            rates["fx_rate"],
        )

    st.divider()

    render_holdings_allocation(holdings_quotes_positions)


with tabs[1]:
    if not account_symbols:
        st.info("No open positions found for account.")
    else:
        assert (
            holdings_metrics is not None
            and holdings_close_norm is not None
            and portfolio_metrics is not None
            and portfolio_close_norm is not None
            and portfolio_correlation_matrix is not None
        )
        render_holdings_performance(
            holdings_metrics,
            holdings_close_norm,
            portfolio_metrics,
            portfolio_close_norm,
            benchmark_metrics,
            benchmark_close_norm,
            risk_free_rate=rates["rf_rate"],
        )

        render_correlation_matrix(portfolio_correlation_matrix)
