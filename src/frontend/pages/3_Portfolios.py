import logging

import pandas as pd
import streamlit as st

from frontend.services.streamlit_data import (
    check_missing_symbols,
    load_account_details,
    load_account_records,
    load_portfolio_snapshot,
    load_security_data,
)
from frontend.shared.dataframe import (
    add_last_indicators,
    add_sparkline,
    add_trade_signal,
    build_security_analytics,
    combine_header_data,
    make_scalar_wide_df,
    make_timeseries_long_df,
    make_timeseries_wide_df,
)
from frontend.shared.jobs import (
    auto_refresh_if_missing,
    check_job_status,
    render_refresh_job_ui,
    start_refresh_job,
)
from frontend.widgets.allocation import render_portfolio_allocation
from frontend.widgets.correlation import render_correlation_matrix
from frontend.widgets.intraday import render_portfolio_intraday
from frontend.widgets.kpis import (
    render_account_summary,
    render_market_snapshot,
    render_status_strip,
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

# --- Session state -----------------------------------------------------------
try:
    account_id = st.session_state["account_id"]
    hide_balances = st.session_state["hide_balances_toggle"]

    start_date = st.session_state["start_date"]
    end_date = st.session_state["end_date"]

    header_symbols = st.session_state["header_symbols"]
    benchmark_symbols = st.session_state["benchmark_symbols"]
    base_symbols = st.session_state["base_symbols"]

    benchmark = st.session_state["benchmark"]

    rates = st.session_state["rates"]

except KeyError as exc:
    st.error("App state is not initialized. Please refresh browser.")
    logger.exception("Missing session key on Holdings page: %s", exc)
    st.stop()

# --- Load account details -----------------------------------------------------
account = load_account_details(account_id)

# -- Render header ------------------------------------------------------------
h = st.columns([6, 1], vertical_alignment="center")
with h[0]:
    st.markdown(f"## 📊 {account.type} Portfolio")

# --- Auto job status checking ------------------------------------------------
check_job_status()
render_refresh_job_ui(active_page)

# --- Load account records -----------------------------------------------------
records = load_account_records(account.id)

# --- Load portfolio symbols -------------------------------------------------------
portfolio_symbols = sorted(set(p["symbol"] for p in records.open_positions))
st.session_state["portfolio_symbols"] = portfolio_symbols
page_symbols = sorted(set(portfolio_symbols + base_symbols))
st.session_state["page_symbols"] = page_symbols

# --- Ensure all page symbols are available else blocking refresh job --------
missing_symbols = sorted(check_missing_symbols(tuple(page_symbols)))
auto_refresh_if_missing(missing_symbols, active_page, start_date, end_date)

# --- Load base data (header + benchmark only) ------------------------------
securities = load_security_data(base_symbols, start_date, end_date)

# --- Load portfolio data ---------------------------------------------------
portfolio = load_portfolio_snapshot(account.id, start_date, end_date)
st.session_state["portfolio_value"] = portfolio.summary["total_value"]
st.session_state["cash_balance"] = portfolio.summary["cash_balance"]

# --- Render refresh data button -----------------------------------------------
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
            active_page=active_page,
            start_date=start_date,
            end_date=end_date,
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
render_status_strip(rates)

if not hide_balances:
    render_account_summary(
        account.number, account.type, account.name, portfolio.summary
    )

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


# --- Holdings + portfolio data (only when account has positions) -------------
holdings_data = None
holdings_close_norm = None
portfolio_metrics = None
portfolio_close_norm = None
portfolio_correlation_matrix = None

if portfolio_symbols:
    holdings_positions = make_scalar_wide_df(portfolio.holdings)
    holdings_positions["symbol"] = holdings_positions.index

    holdings_analytics = build_security_analytics(
        portfolio_symbols, portfolio.securities
    )
    holdings_close_norm = holdings_analytics.close_norm
    holdings_positions = add_sparkline(
        holdings_positions, holdings_analytics.closes, add_intraday_close=True
    )

    new_cols = holdings_analytics.metrics.columns.difference(holdings_positions.columns)
    holdings_data = holdings_positions.join(
        holdings_analytics.metrics[new_cols], how="left"
    )
    st.session_state["portfolio_holdings_qty"] = {
        s: int(holdings_positions.loc[s, "open_qty"])
        for s in portfolio_symbols
        if s in holdings_positions.index
    }

    # Portfolio dataframes
    portfolio_metrics = make_scalar_wide_df(portfolio.metrics)
    portfolio_metrics = portfolio_metrics.set_index("symbol", drop=False)

    portfolio_indicators = make_timeseries_long_df(portfolio.indicators)
    portfolio_closes = make_timeseries_wide_df(portfolio_indicators, "close")
    portfolio_close_norm = make_timeseries_wide_df(portfolio_indicators, "close_norm")

    portfolio_correlation_matrix = pd.DataFrame(portfolio.correlation_matrix["entries"])
    portfolio_correlation_matrix = portfolio_correlation_matrix.pivot(
        index="row", columns="col", values="value"
    )

    portfolio_metrics = add_sparkline(portfolio_metrics, portfolio_closes)
    portfolio_metrics = add_last_indicators(portfolio_metrics, portfolio_indicators)
    portfolio_metrics = add_trade_signal(portfolio_metrics)

# --- Account records dataframes ---------------------------------------------------
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
        "Allocation",
        "Performance",
        "Optimization",
        "Correlation",
        "Records",
    ]
)

with tabs[0]:
    render_portfolio_positions(holdings_data)

with tabs[1]:
    render_portfolio_allocation(portfolio.summary, holdings_data)

with tabs[2]:
    render_performance_view(
        metrics=holdings_data,
        close_norm_eod=holdings_close_norm,
        benchmark_metrics=benchmark_data,
        benchmark_close_norm_eod=benchmark_close_norm,
        risk_free_rate=rates["rf_rate"],
        key_prefix="holdings",
        portfolio_metrics=portfolio_metrics,
        portfolio_close_norm_eod=portfolio_close_norm,
        use_group_filter=False,
    )

with tabs[3]:
    render_optimizer(
        portfolio_symbols=portfolio_symbols,
        holdings_data=holdings_data,
        portfolio_metrics=portfolio_metrics,
        account_id=account_id,
        benchmark_data=benchmark_data,
        risk_free_rate=rates["rf_rate"],
    )

with tabs[4]:
    render_correlation_matrix(portfolio_correlation_matrix)


with tabs[5]:
    start_date, end_date = render_records_header(transactions)
    if start_date:
        render_closed_lots_table(closed_lots, account.tax_status, start_date, end_date)
        render_cash_flows_table(cash_flows, start_date, end_date)
        render_transactions_table(transactions, start_date, end_date)
