import logging

import streamlit as st

from frontend.presentation.tabs.intraday import (
    render_market_intraday,
    render_market_movers,
)
from frontend.presentation.tabs.performance import (
    render_performance_view,
    render_statistics_table,
)
from frontend.presentation.widgets.kpis import (
    render_market_snapshot,
    render_status_strip,
)
from frontend.services.streamlit_data import check_missing_symbols, load_security_data
from frontend.shared.config_loader import load_symbols_config
from frontend.utils.dataframe import (
    add_last_indicators,
    add_sparkline,
    combine_header_data,
    make_scalar_wide_df,
    make_timeseries_long_df,
    make_timeseries_wide_df,
)
from frontend.utils.jobs import (
    auto_refresh_if_missing,
    check_job_status,
    render_refresh_job_ui,
    start_refresh_job,
)
from frontend.utils.market import create_mover_groups

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


# -- Render header ------------------------------------------------------------
h = st.columns([6, 1], vertical_alignment="center")
with h[0]:
    st.markdown("## 🏦 ETF Market")

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

# --- Load base + market securities data ---------------------------------------
securities = load_security_data(page_symbols, start_date, end_date)

# --- Render refresh data button -----------------------------------------------
with h[1]:
    market_refresh = st.button(
        "Refresh Data",
        icon=":material/refresh:",
        type="secondary",
        key="market_refresh_button",
        width="stretch",
    )
    if market_refresh:
        start_refresh_job(
            symbols=page_symbols,
            blocking=True,
            active_page=active_page,
            start_date=start_date,
            end_date=end_date,
        )


# --- Header dataframes ---------------------------------------------------
header_quotes = combine_header_data(header_symbols, securities)
st.session_state["last_us_timestamp"] = header_quotes[
    (header_quotes["currency"] == "USD")
]["timestamp"].max()
st.session_state["last_ca_timestamp"] = header_quotes[
    header_quotes["currency"] == "CAD"
]["timestamp"].max()

# --- Render KPIs --------------------------------------------------------------------
render_status_strip(rates)

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

# --- Market dataframes -------------------------------------------------------
# Market quotes
market_quotes = make_scalar_wide_df(
    {s: securities.quote[s] for s in market_etf_symbols}
)
market_quotes["symbol"] = market_quotes.index

# Market metrics
market_metrics = make_scalar_wide_df(
    {s: securities.metrics[s] for s in market_etf_symbols}
)
market_profiles = make_scalar_wide_df(
    {s: securities.profile[s] for s in market_etf_symbols}
)

# Market bars & indicators
market_bars = make_timeseries_long_df(
    {s: securities.bars[s] for s in market_etf_symbols}
)
market_indicators = make_timeseries_long_df(
    {s: securities.indicators[s] for s in market_etf_symbols}
)

# Market closes & close norms
market_closes = make_timeseries_wide_df(market_indicators, "close")
market_close_norm = make_timeseries_wide_df(market_indicators, "close_norm")

# Add sparklines
market_quotes = add_sparkline(market_quotes, market_closes, add_intraday_close=True)
market_metrics = add_sparkline(market_metrics, market_closes)
market_metrics = add_last_indicators(market_metrics, market_indicators)

# Create extended groups for market movers
etf_groups = create_mover_groups(market_quotes, symbols_config.base_market_etfs)

# --- Tabs ----------------------------------------
tabs = st.tabs(["Movers", "Intraday", "Performance", "Statistics"])

with tabs[0]:
    render_market_movers(market_quotes, market_type="ETF")

with tabs[1]:
    render_market_intraday(
        market_data=market_quotes,
        groups=symbols_config.base_market_etfs,
        market_type="ETF",
        key_prefix="market-etf",
    )

with tabs[2]:
    render_performance_view(
        risk_free_rate=rates["rf_rate"],
        key_prefix="market-etf",
        benchmark_metrics=benchmark_metrics,
        benchmark_close_norm_eod=benchmark_close_norm,
        metrics=market_metrics,
        close_norm_eod=market_close_norm,
        use_group_filter=True,
        groups=etf_groups,
    )

with tabs[3]:
    render_statistics_table(
        key_prefix="market-etf",
        benchmark_metrics=benchmark_metrics,
        securities_metrics=market_metrics,
        portfolio_metrics=None,
    )
