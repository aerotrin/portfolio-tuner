import logging

import streamlit as st

from frontend.services.streamlit_data import check_missing_symbols, load_security_data
from frontend.shared.symbols_loader import load_symbols_config
from frontend.shared.dataframe import (
    add_sparkline,
    build_security_analytics,
    combine_header_data,
    make_scalar_wide_df,
)
from frontend.shared.jobs import (
    auto_refresh_if_missing,
    check_job_status,
    maybe_auto_refresh_data,
    render_refresh_job_ui,
    start_refresh_job,
)
from frontend.widgets.correlation import render_market_correlation
from frontend.widgets.intraday import render_market_intraday
from frontend.widgets.kpis import render_market_snapshot, render_status_inline
from frontend.widgets.movers import render_market_movers
from frontend.widgets.optimizer import render_optimizer
from frontend.widgets.performance import render_performance_view

logger = logging.getLogger(__name__)

active_page = "market_etf"
st.session_state["active_page"] = active_page

# --- Session state -----------------------------------------------------------
try:
    start_date = st.session_state["start_date"]
    end_date = st.session_state["end_date"]

    header_symbols = st.session_state["header_symbols"]
    benchmark_symbols = st.session_state["benchmark_symbols"]
    base_symbols = st.session_state["base_symbols"]

    market_etf_symbols = st.session_state["market_etf_symbols"]
    benchmark = st.session_state["benchmark"]

    rates = st.session_state["rates"]

except KeyError as exc:
    st.error("App state is not initialized. Please refresh browser.")
    logger.exception("Missing session key on Market page: %s", exc)
    st.stop()

symbols_config = load_symbols_config()


# -- Render header: title + status/refresh cluster in one row -----------------
with st.container(
    horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"
):
    st.markdown("### 🏦 ETF Market", width="content")
    # Nested content-width container keeps the cluster tight on the right
    with st.container(horizontal=True, vertical_alignment="center", width="content"):
        render_status_inline(rates, active_page)
        # Click handled below, once page_symbols is computed
        market_refresh = st.button(
            "Refresh Data",
            icon=":material/refresh:",
            type="secondary",
            key="market_refresh_button",
        )

# --- Auto job status checking ------------------------------------------------
check_job_status()
render_refresh_job_ui(active_page)

# --- Page symbols -----------------------------------------------------------
page_symbols = sorted(
    {
        *header_symbols,
        *benchmark_symbols,
        *market_etf_symbols,
    }
)
st.session_state["page_symbols"] = page_symbols

# --- Ensure all page symbols are available else blocking refresh job --------
missing_symbols = sorted(check_missing_symbols(tuple(page_symbols)))
auto_refresh_if_missing(missing_symbols, active_page, start_date, end_date)

# --- Timed / first-visit background refresh (Auto Refresh toggle) ------------
maybe_auto_refresh_data()

# --- Handle Refresh Data click (button rendered in the header row) -----------
if market_refresh:
    start_refresh_job(
        symbols=page_symbols,
        blocking=False,
        active_page=active_page,
        start_date=start_date,
        end_date=end_date,
    )

# --- Load base + market securities data ---------------------------------------
securities = load_security_data(page_symbols, start_date, end_date)

# --- Header dataframes ---------------------------------------------------
header_quotes = combine_header_data(header_symbols, securities)
st.session_state["last_us_timestamp"] = header_quotes[
    (header_quotes["currency"] == "USD")
]["timestamp"].max()
st.session_state["last_ca_timestamp"] = header_quotes[
    header_quotes["currency"] == "CAD"
]["timestamp"].max()

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

# --- Market dataframes -------------------------------------------------------
market_quotes = make_scalar_wide_df(
    {s: securities.quote[s] for s in market_etf_symbols}
)
market_quotes["symbol"] = market_quotes.index

market_analytics = build_security_analytics(market_etf_symbols, securities)
market_close_norm = market_analytics.close_norm
market_quotes = add_sparkline(
    market_quotes, market_analytics.closes, add_intraday_close=True
)

new_cols = market_analytics.metrics.columns.difference(market_quotes.columns)
market_data = market_quotes.join(market_analytics.metrics[new_cols], how="left")

# --- Tabs ----------------------------------------
tabs = st.tabs(["Movers", "Intraday", "Performance", "Correlation", "Optimization"])

with tabs[0]:
    render_market_movers(market_data, market_type="ETF")

with tabs[1]:
    render_market_intraday(
        market_data=market_data,
        groups=symbols_config.base_market_etfs,
        market_type="ETF",
        key_prefix="market-etf",
    )

with tabs[2]:
    chart_symbols = render_performance_view(
        risk_free_rate=rates["rf_rate"],
        key_prefix="market-etf",
        benchmark_metrics=benchmark_data,
        benchmark_close_norm_eod=benchmark_close_norm,
        metrics=market_data,
        close_norm_eod=market_close_norm,
        use_group_filter=True,
        groups=symbols_config.base_market_etfs,
    )

with tabs[3]:
    render_market_correlation(market_analytics.closes, chart_symbols)

with tabs[4]:
    render_optimizer(
        portfolio_symbols=chart_symbols,
        holdings_data=None,
        portfolio_metrics=None,
        context_id="market-etf",
        context_label="Research",
        benchmark_data=benchmark_data,
        risk_free_rate=rates["rf_rate"],
        data_source_label="Performance tab selection",
    )
