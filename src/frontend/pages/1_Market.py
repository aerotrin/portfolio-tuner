import logging
from typing import Any

import streamlit as st

from frontend.presentation.settings import MOVER_SHOW_COUNT
from frontend.presentation.tabs.intraday import render_market_intraday
from frontend.presentation.tabs.performance import render_performance_view
from frontend.presentation.widgets.kpis import (
    render_market_snapshot,
    render_status_strip,
)
from frontend.services.streamlit_data import load_security_data
from frontend.shared.config_loader import SymbolGroup, load_symbols_config
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

active_page = "market"

# --- Session state -----------------------------------------------------------
try:
    start_date = st.session_state["start_date"]
    end_date = st.session_state["end_date"]

    header_symbols = st.session_state["header_symbols"]
    benchmark_symbols = st.session_state["benchmark_symbols"]
    base_symbols = st.session_state["base_symbols"]

    market_symbols = st.session_state["market_symbols"]
    benchmark = st.session_state["benchmark"]

    available_symbols = st.session_state["available_symbols"]
    rates = st.session_state["rates"]

except KeyError as exc:
    st.error("App state is not initialized. Please refresh browser.")
    logger.exception("Missing session key on Market page: %s", exc)
    st.stop()

symbols_config = load_symbols_config()  # TODO: Duplication with app.py


# -- Render header ------------------------------------------------------------
h = st.columns([6, 1], vertical_alignment="center")
with h[0]:
    st.markdown("## 🏦 Market Watch")

# --- Auto job status checking ------------------------------------------------
check_job_status()
render_refresh_job_ui(active_page)

# --- Page symbols -----------------------------------------------------------
page_symbols = sorted(
    {
        *header_symbols,
        *benchmark_symbols,
        *market_symbols,
    }
)

# --- Ensure all page symbols are available else blocking refresh job --------
missing_symbols = sorted(set(page_symbols) - set(available_symbols))
if missing_symbols:
    start_refresh_job(
        symbols=missing_symbols,
        blocking=True,
        intraday=True,
        active_page=active_page,
        start_date=start_date,
        end_date=end_date,
    )

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
            intraday=True,
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
market_quotes = make_scalar_wide_df({s: securities.quote[s] for s in market_symbols})
market_quotes["symbol"] = market_quotes.index

# Market metrics
market_metrics = make_scalar_wide_df({s: securities.metrics[s] for s in market_symbols})
market_profiles = make_scalar_wide_df(
    {s: securities.profile[s] for s in market_symbols}
)

# Market bars & indicators
market_bars = make_timeseries_long_df({s: securities.bars[s] for s in market_symbols})
market_indicators = make_timeseries_long_df(
    {s: securities.indicators[s] for s in market_symbols}
)

# Market closes & close norms
market_closes = make_timeseries_wide_df(market_indicators, "close")
market_close_norm = make_timeseries_wide_df(market_indicators, "close_norm")

# Add sparklines
market_quotes = add_sparkline(market_quotes, market_closes, add_intraday_close=True)
market_metrics = add_sparkline(market_metrics, market_closes)
market_metrics = add_last_indicators(market_metrics, market_indicators)

# Filter stocks and etfs
stocks_symbols = st.session_state["market_stock_symbols"]
etfs_symbols = st.session_state["market_etf_symbols"]

mask_stocks = market_quotes.index.isin(stocks_symbols)
mask_etfs = market_quotes.index.isin(etfs_symbols)
stocks_quotes = market_quotes.loc[mask_stocks]
etfs_quotes = market_quotes.loc[mask_etfs]

stocks_metrics = market_metrics.loc[market_metrics.index.isin(stocks_symbols)]
etfs_metrics = market_metrics.loc[market_metrics.index.isin(etfs_symbols)]


def create_mover_groups(
    quotes: Any,
    base_groups: list[SymbolGroup],
) -> list[SymbolGroup]:
    """Create mover groups (most active, gainers, losers) for CAD and USD currencies."""
    mover_groups = []

    for currency in ["USD", "CAD"]:
        sub_quotes = quotes[quotes["currency"] == currency]
        country = "US" if currency == "USD" else "Canada"

        # Most active (by volume)
        most_active = (
            sub_quotes.sort_values(by="volume", ascending=False)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if most_active:
            mover_groups.append(
                SymbolGroup(
                    label=f"Most Active {country}",
                    symbols=tuple(most_active),
                )
            )

        # Top gainers (by change_percent descending)
        gainers = (
            sub_quotes[sub_quotes["change_percent"] > 0]
            .sort_values(by="change_percent", ascending=False)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if gainers:
            mover_groups.append(
                SymbolGroup(
                    label=f"Top Gainers {country}",
                    symbols=tuple(gainers),
                )
            )

        # Top losers (by change_percent ascending)
        losers = (
            sub_quotes[sub_quotes["change_percent"] < 0]
            .sort_values(by="change_percent", ascending=True)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if losers:
            mover_groups.append(
                SymbolGroup(
                    label=f"Top Losers {country}",
                    symbols=tuple(losers),
                )
            )

    return mover_groups + base_groups


# Create extended groups for market movers
etf_groups = create_mover_groups(etfs_quotes, symbols_config.base_market_etfs)
stock_groups = create_mover_groups(stocks_quotes, symbols_config.base_market_stocks)

# --- Tabs (all use prebuilt market and benchmark data) ----------------------------------------
tabs = st.tabs(
    [
        "ETF Movers",
        "ETF Performance",
        "Stock Movers",
        "Stock Performance",
    ]
)

with tabs[0]:  # ETF Movers
    render_market_intraday(
        etfs_quotes,
        symbols_config.base_market_etfs,
        type="ETF",
        key_prefix="market-etf",
    )


with tabs[1]:  # ETF Performance
    render_performance_view(
        metrics_eod=etfs_metrics,
        close_norm_eod=market_close_norm,
        benchmark_metrics_eod=benchmark_metrics,
        benchmark_close_norm_eod=benchmark_close_norm,
        risk_free_rate=rates["rf_rate"],
        key_prefix="market-etf",
        use_group_filter=True,
        groups=etf_groups,
    )

with tabs[2]:  # Stock Movers
    render_market_intraday(
        stocks_quotes,
        symbols_config.base_market_stocks,
        type="stock",
        key_prefix="market-stock",
    )


with tabs[3]:  # Stock Performance
    render_performance_view(
        metrics_eod=stocks_metrics,
        close_norm_eod=market_close_norm,
        benchmark_metrics_eod=benchmark_metrics,
        benchmark_close_norm_eod=benchmark_close_norm,
        risk_free_rate=rates["rf_rate"],
        key_prefix="market-stock",
        use_group_filter=True,
        groups=stock_groups,
    )
