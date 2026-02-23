import logging

import pandas as pd
import streamlit as st

from frontend.presentation.tabs.intraday import render_portfolio_intraday
from frontend.presentation.tabs.performance import render_performance_view
from frontend.presentation.tabs.reports import (
    render_cash_flows_table,
    render_closed_lots_table,
    render_reports_header,
    render_transactions_table,
)
from frontend.presentation.widgets.kpis import (
    render_account_summary,
    render_market_snapshot,
    render_status_strip,
)
from frontend.services.streamlit_data import (
    load_account_details,
    load_account_records,
    load_portfolio_snapshot,
    load_security_data,
)
from frontend.utils.dataframe import (
    add_last_indicators,
    add_sparkline,
    combine_header_data,
    make_scalar_wide_df,
    make_timeseries_long_df,
    make_timeseries_wide_df,
)
from frontend.utils.jobs import (
    check_job_status,
    render_refresh_job_ui,
    start_refresh_job,
)

logger = logging.getLogger(__name__)

active_page = "portfolio"

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

    available_symbols = st.session_state["available_symbols"]
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
page_symbols = sorted(set(portfolio_symbols + base_symbols))

# --- Ensure all page symbols are available else blocking refresh job --------
missing_symbols = sorted(set(page_symbols) - set(available_symbols))
if missing_symbols:
    start_refresh_job(
        symbols=missing_symbols,
        blocking=True,
        intraday=False,
        active_page=active_page,
        start_date=start_date,
        end_date=end_date,
    )


# --- Load base data (header + benchmark only) ------------------------------
securities = load_security_data(base_symbols, start_date, end_date)

# --- Load portfolio data ---------------------------------------------------
portfolio = load_portfolio_snapshot(account.id, start_date, end_date)

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
            intraday=True,
            active_page=active_page,
            start_date=start_date,
            end_date=end_date,
        )

# --- Make header dataframes -------------------------------------------------------
header_quotes = combine_header_data(header_symbols, securities)
st.session_state["last_us_timestamp"] = header_quotes[
    (header_quotes["currency"] == "USD") & (header_quotes["exchange"] == "INDEX")
]["timestamp"].max()  # FTRK-306
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
# Benchmark quotes
benchmark_quotes = combine_header_data([benchmark], securities)

# Benchmark metrics
benchmark_metrics = make_scalar_wide_df({s: securities.metrics[s] for s in [benchmark]})
benchmark_profiles = make_scalar_wide_df(
    {s: securities.profile[s] for s in [benchmark]}
)

# Benchmark bars & indicators
benchmark_bars = make_timeseries_long_df({s: securities.bars[s] for s in [benchmark]})
benchmark_indicators = make_timeseries_long_df(
    {s: securities.indicators[s] for s in [benchmark]}
)

# Benchmark closes & close norms
benchmark_closes = make_timeseries_wide_df(benchmark_indicators, "close")
benchmark_close_norm = make_timeseries_wide_df(benchmark_indicators, "close_norm")

# Add sparklines
benchmark_quotes = add_sparkline(
    benchmark_quotes, benchmark_closes, add_intraday_close=True
)
benchmark_metrics = add_sparkline(benchmark_metrics, benchmark_closes)
benchmark_metrics = add_last_indicators(benchmark_metrics, benchmark_indicators)


# --- Holdings + portfolio data (only when account has positions) -------------
holdings_positions = None
holdings_metrics = None
holdings_close_norm = None
portfolio_metrics = None
portfolio_close_norm = None
portfolio_correlation_matrix = None

if portfolio_symbols:
    holdings_positions = make_scalar_wide_df(portfolio.holdings)
    holdings_positions["symbol"] = holdings_positions.index

    holdings_metrics = make_scalar_wide_df(
        {s: portfolio.securities.metrics[s] for s in portfolio_symbols}
    )
    holdings_profiles = make_scalar_wide_df(
        {s: portfolio.securities.profile[s] for s in portfolio_symbols}
    )

    holdings_bars = make_timeseries_long_df(
        {s: portfolio.securities.bars[s] for s in portfolio_symbols}
    )
    holdings_indicators = make_timeseries_long_df(
        {s: portfolio.securities.indicators[s] for s in portfolio_symbols}
    )
    holdings_closes = make_timeseries_wide_df(holdings_indicators, "close")
    holdings_close_norm = make_timeseries_wide_df(holdings_indicators, "close_norm")

    prof_df = holdings_profiles.loc[
        :, ~holdings_profiles.columns.isin(holdings_positions.columns)
    ]
    holdings_positions = holdings_positions.join(prof_df, how="left")

    holdings_positions = add_sparkline(
        holdings_positions, holdings_closes, add_intraday_close=True
    )
    holdings_metrics = add_sparkline(holdings_metrics, holdings_closes)
    holdings_metrics = add_last_indicators(holdings_metrics, holdings_indicators)

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
tabs = st.tabs(["Positions", "Performance", "Reports"])

with tabs[0]:
    render_portfolio_intraday(
        holdings_positions,
        portfolio.summary,
        account.id,
        account.name,
        rates["fx_rate"],
    )

with tabs[1]:
    if not portfolio_symbols:
        st.info("No open positions found for account.")
    else:
        assert (
            holdings_metrics is not None
            and holdings_close_norm is not None
            and portfolio_metrics is not None
            and portfolio_close_norm is not None
            and portfolio_correlation_matrix is not None
        )

        render_performance_view(
            metrics_eod=holdings_metrics,
            close_norm_eod=holdings_close_norm,
            benchmark_metrics_eod=benchmark_metrics,
            benchmark_close_norm_eod=benchmark_close_norm,
            risk_free_rate=rates["rf_rate"],
            key_prefix="holdings",
            portfolio_metrics_eod=portfolio_metrics,
            portfolio_close_norm_eod=portfolio_close_norm,
            correlation_matrix=portfolio_correlation_matrix,
            use_group_filter=False,
        )

with tabs[2]:
    if not transactions.empty:
        start_date, end_date = render_reports_header(transactions)
        render_closed_lots_table(closed_lots, account.tax_status, start_date, end_date)
        render_cash_flows_table(cash_flows, start_date, end_date)
        render_transactions_table(transactions, start_date, end_date)
    else:
        st.info("No transactions found.")
