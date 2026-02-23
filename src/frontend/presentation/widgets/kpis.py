from datetime import datetime

import pandas as pd
import streamlit as st

from frontend.presentation.settings import HEIGHT_MARKET_SNAPSHOT
from frontend.utils.time import humanize_timestamp


def render_account_summary(
    account_number: str, account_type: str, account_owner: str, portfolio_summary: dict
) -> None:
    """Draw KPIs for the balances of a selected portfolio."""

    with st.container(border=True, horizontal=True):
        st.metric(
            f"{account_type} #{account_number}",
            account_owner,
        )
        st.metric(
            "Current Value CAD",
            f"${portfolio_summary['total_value']:,.2f}",
        )
        st.metric(
            "Unrealized P/L CAD",
            f"${portfolio_summary['unrealized_gain']:,.2f}",
            f"{portfolio_summary['pnl_intraday']:+,.2f}",
        )
        st.metric(
            "Cash CAD",
            f"${portfolio_summary['cash_balance']:,.2f}",
            f"{portfolio_summary['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
        )
        st.metric(
            "Securities CAD",
            f"${portfolio_summary['market_value']:,.2f}",
            f"{1 - portfolio_summary['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
        )
        st.metric(
            "Return CAD/IRR%",
            f"${portfolio_summary['total_value'] - portfolio_summary['net_investment']:,.2f}",
            "TBD",  # TODO: Add IRR calculation
            delta_color="off",  # TODO: Remove
            delta_arrow="off",  # TODO: Remove
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
            last_us_timestamp.tz_convert("UTC")
        )

    if not last_ca_timestamp or pd.isna(last_ca_timestamp):
        last_ca_timestamp_natural = "N/A"
        color_ca = "gray"
    else:
        last_ca_timestamp_natural, _, color_ca = humanize_timestamp(
            last_ca_timestamp.tz_convert("UTC")
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
                delta=f"{row['change_percent']:+.2%}",
                border=True,
                chart_data=row["sparkline"],
                chart_type="area",
                height=HEIGHT_MARKET_SNAPSHOT,
            )


def render_portfolio_kpis(df: pd.DataFrame) -> None:
    """Render the portfolio KPIs."""
    st.metric(
        "Current P/L CAD",
        f"${df['gain'].sum():,.2f}",
        f"{df['intraday_change'].sum():+,.2f}",
    )
    st.metric(
        "Day Best Performer CAD",
        f"{df['symbol'][df['intraday_change'].idxmax()]}",
        f"{df['intraday_change'].max():+,.2f}",
    )
    st.metric(
        "Day Worst Performer CAD",
        f"{df['symbol'][df['intraday_change'].idxmin()]}",
        f"{df['intraday_change'].min():+,.2f}",
    )
    st.metric(
        "Total FX Exposure",
        f"${df['fx_exposure'].sum():,.2f}",
    )
    st.metric("No. of Holdings", f"{len(df)}")
    st.metric(
        "Average Days Open",
        f"{df['days_held'].mean():.0f}",
    )


def render_health_bar(df: pd.DataFrame) -> None:
    """Render the health bar."""
    g = df["gain_pct"].gt(0).sum()
    l = df["gain_pct"].lt(0).sum()
    health_bar = "🟩" * g + "🟥" * l
    st.caption(f"{health_bar}   |   {len(df)} positions (↑ {g}, ↓ {l})")
