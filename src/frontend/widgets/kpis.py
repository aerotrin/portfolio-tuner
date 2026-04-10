from datetime import datetime

import pandas as pd
import streamlit as st

from frontend.shared.settings import HEIGHT_MARKET_SNAPSHOT
from frontend.shared.time import humanize_timestamp


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
            "Total Value",
            f"${portfolio_summary['total_value']:,.2f} CAD",
        )
        st.metric(
            "Unrealized P/L",
            f"${portfolio_summary['unrealized_gain']:,.2f} CAD",
            f"{portfolio_summary['return_on_cost']:+.2%}",
        )
        st.metric(
            "Total Return | MWRR",
            f"${portfolio_summary['total_value'] - portfolio_summary['net_investment']:,.2f} CAD",
            f"{portfolio_summary['mwrr']:+.2%}",
        )
        st.metric(
            "Securities",
            f"${portfolio_summary['market_value']:,.2f} CAD",
            f"{1 - portfolio_summary['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
            delta_description="of portfolio",
        )
        st.metric(
            "Cash",
            f"${portfolio_summary['cash_balance']:,.2f} CAD",
            f"{portfolio_summary['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
            delta_description="of portfolio",
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
        "Securities Value Intraday",
        f"${df['market_value'].sum():,.2f} CAD",
        f"{df['intraday_change'].sum():+,.2f} CAD",
    )
    st.metric(
        "Best Intraday",
        f"{df['symbol'][df['intraday_change'].idxmax()]}",
        f"{df['intraday_change'].max():+,.2f} CAD",
    )
    st.metric(
        "Worst Intraday",
        f"{df['symbol'][df['intraday_change'].idxmin()]}",
        f"{df['intraday_change'].min():+,.2f} CAD",
    )
    st.metric(
        "Total FX Exposure",
        f"${df['fx_exposure'].sum():,.2f} CAD",
    )
    st.metric("No. of Holdings", f"{len(df)}")
    st.metric(
        "Average Days Open",
        f"{df['days_held'].mean():.0f}",
    )


def render_positions_health_bar(df: pd.DataFrame) -> None:
    """Render the health bar."""
    gainers = df["gain_pct"].gt(0).sum()
    losers = df["gain_pct"].lt(0).sum()
    health_bar = "🟩" * gainers + "🟥" * losers
    st.caption(f"{health_bar}   |   {len(df)} positions (↑ {gainers}, ↓ {losers})")


def render_intraday_health_bar(df: pd.DataFrame) -> None:
    """Render the health bar."""
    gainers = df["change_percent"].gt(0).sum()
    losers = df["change_percent"].lt(0).sum()
    health_bar = "🟩" * gainers + "🟥" * losers
    st.caption(f"{health_bar}   |   {len(df)} securities (↑ {gainers}, ↓ {losers})")
