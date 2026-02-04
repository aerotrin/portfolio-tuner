from datetime import datetime

import pandas as pd
import streamlit as st

from src.presentation.settings import HEIGHT_MARKET_SNAPSHOT
from src.utils.time import humanize_timestamp


def render_account_summary() -> None:
    """Draw KPIs for the balances of a selected portfolio."""
    account_name = st.session_state["account_name"]
    account_owner = st.session_state["account_owner"]
    account_kpis = st.session_state["account_summary"]
    portfolio_kpis = st.session_state["portfolio_summary"]

    with st.container(border=True, horizontal=True):
        st.metric(
            account_name,
            account_owner,
        )
        st.metric(
            "Current Value CAD",
            f"${portfolio_kpis['total_value']:,.2f}",
        )
        st.metric(
            "Unrealized P/L CAD",
            f"${portfolio_kpis['unrealized_gain']:,.2f}",
            f"{portfolio_kpis['pnl_intraday']:+,.2f}",
        )
        st.metric(
            "Cash CAD",
            f"${account_kpis['cash_balance']:,.2f}",
            f"{portfolio_kpis['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
        )
        st.metric(
            "Securities CAD",
            f"${portfolio_kpis['market_value']:,.2f}",
            f"{1 - portfolio_kpis['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
        )
        st.metric(
            "Total Return CAD",
            f"${portfolio_kpis['total_value'] - account_kpis['net_investment']:,.2f}",
        )


def render_status_strip(rates: dict) -> None:
    """
    Render the status strip.
    """
    last_us_timestamp = st.session_state.get("last_us_timestamp")
    last_ca_timestamp = st.session_state.get("last_ca_timestamp")

    if not last_us_timestamp or pd.isna(last_us_timestamp):
        last_us_timestamp_natural = "N/A"
        color_us = "gray"
    else:
        last_us_timestamp_natural, _, color_us = humanize_timestamp(
            last_us_timestamp.tz_localize("UTC")
        )

    if not last_ca_timestamp or pd.isna(last_ca_timestamp):
        last_ca_timestamp_natural = "N/A"
        color_ca = "gray"
    else:
        last_ca_timestamp_natural, _, color_ca = humanize_timestamp(
            last_ca_timestamp.tz_localize("UTC")
        )

    with st.container(horizontal=True, border=False):
        st.caption(datetime.now().strftime("%a %Y-%m-%d %I:%M:%S %p %Z"))
        st.caption(f"USD/CAD: {rates['fx_rate']:.3f}")
        st.caption(f"T-Bill 6m: {rates['rf_rate']:.2f}%")
        st.badge(f"{last_ca_timestamp_natural}", icon="🇨🇦", color=color_ca)
        st.badge(f"{last_us_timestamp_natural}", icon="🇺🇸", color=color_us)
        if st.session_state.get("live_data_toggle", False):
            st.badge("Live data mode", icon="🔄", color="blue")


def render_market_snapshot(header_data: pd.DataFrame) -> None:
    """
    Render the index metrics cards.
    """
    if header_data is None or header_data.empty:
        st.info("No market snapshot data available.")
        return

    df = header_data.copy()

    with st.container():
        c = st.columns(df.shape[0], border=False)
        for i, (_, row) in enumerate(df.iterrows()):
            c[i].metric(
                f"{row['name']}",
                value=f"${row['close']:,.2f}",
                delta=f"{row['changePercent']:+.2%}",
                border=True,
                chart_data=row["sparkline"],
                chart_type="area",
                height=HEIGHT_MARKET_SNAPSHOT,
            )
