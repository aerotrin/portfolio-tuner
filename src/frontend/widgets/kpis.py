from datetime import datetime

from frontend.shared.settings import (
    DONUT_CASH_COLOR,
    DONUT_SECURITIES_COLOR,
    HEIGHT_ACCOUNT_DONUT,
    HEIGHT_MARKET_SNAPSHOT,
)
from frontend.shared.time import humanize_timestamp
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _humanize_timestamp_or_na(timestamp: pd.Timestamp | None) -> tuple[str, str]:
    """Format a timestamp for display, falling back to N/A when missing."""
    if not timestamp or pd.isna(timestamp):
        return "N/A", "gray"
    natural, _, color = humanize_timestamp(timestamp.tz_convert("UTC"))
    return natural, color


def _render_cash_securities_donut(
    cash_balance: float, securities_value: float
) -> go.Figure:
    """Tiny donut showing the cash / securities split."""
    total = cash_balance + securities_value
    securities_pct = securities_value / total if total else 0
    fig = go.Figure(
        go.Pie(
            labels=["Securities", "Cash"],
            values=[securities_value, cash_balance],
            hole=0.7,
            sort=False,
            direction="clockwise",
            marker=dict(colors=[DONUT_SECURITIES_COLOR, DONUT_CASH_COLOR]),
            textinfo="none",
            hovertemplate="%{label}: $%{value:,.2f} CAD<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=0, l=0, r=0),
        height=HEIGHT_ACCOUNT_DONUT,
        annotations=[
            dict(
                text=f"{securities_pct:.0%}",
                x=0.5,
                y=0.5,
                font=dict(size=13),
                showarrow=False,
            )
        ],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_account_summary(
    account_number: str, account_type: str, account_owner: str, portfolio_summary: dict
) -> None:
    """Draw KPIs for the balances of a selected portfolio."""

    last_us_timestamp = st.session_state.get("last_us_timestamp")
    last_ca_timestamp = st.session_state.get("last_ca_timestamp")
    latest_timestamp = max(
        (ts for ts in (last_us_timestamp, last_ca_timestamp) if ts and not pd.isna(ts)),
        default=None,
    )
    last_update_natural, last_update_color = _humanize_timestamp_or_na(latest_timestamp)

    with st.container(border=True, horizontal=True, width="stretch"):
        st.metric(
            f"{account_type} #{account_number}",
            account_owner,
            border=False,
        )
        st.metric(
            "Total Value",
            f"${portfolio_summary['total_value']:,.2f} CAD",
            last_update_natural,
            delta_color=last_update_color,
            delta_arrow="off",
            border=False,
        )
        st.metric(
            "Unrealized P/L",
            f"${portfolio_summary['unrealized_gain']:,.2f} CAD",
            f"{portfolio_summary['return_on_cost']:+.2%}",
            border=False,
        )
        st.metric(
            "Total Return | MWRR",
            f"${portfolio_summary['total_value'] - portfolio_summary['net_investment']:,.2f} CAD",
            f"{portfolio_summary['mwrr']:+.2%}",
            border=False,
        )
        with st.container(border=False):
            st.plotly_chart(
                _render_cash_securities_donut(
                    portfolio_summary["cash_balance"],
                    portfolio_summary["total_value"]
                    - portfolio_summary["cash_balance"],
                ),
                config={"displayModeBar": False},
            )
        st.metric(
            "Cash",
            f"${portfolio_summary['cash_balance']:,.2f} CAD",
            f"{portfolio_summary['cash_pct']:.1%}",
            delta_color="off",
            delta_arrow="off",
            delta_description="of portfolio",
            border=False,
        )


def render_status_strip(rates: dict) -> None:
    """
    Render the status strip.
    """
    with st.container(horizontal=True, border=False):
        st.caption(datetime.now().strftime("%a %Y-%m-%d %I:%M:%S %p %Z"))
        st.caption(f"USD/CAD: {rates['fx_rate']:.3f}")
        st.caption(f"T-Bill 6m: {rates['rf_rate']:.2f}%")
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
