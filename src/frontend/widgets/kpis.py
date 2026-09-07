from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.shared.jobs import render_auto_refresh_toggle
from frontend.shared.settings import (
    DONUT_CASH_COLOR,
    DONUT_SECURITIES_COLOR,
    HEIGHT_ACCOUNT_DONUT,
    HEIGHT_MARKET_SNAPSHOT,
    MASKED_VALUE,
    SNAPSHOT_DISPLAY_NAMES,
)
from frontend.shared.time import humanize_timestamp


def _humanize_timestamp_or_na(
    timestamp: str | pd.Timestamp | None,
) -> tuple[str, Literal["blue", "yellow", "gray"]]:
    """Format a timestamp for display, falling back to N/A when missing."""
    if timestamp is None or pd.isna(timestamp):
        return "N/A", "gray"
    natural, _, color = humanize_timestamp(timestamp)
    return natural, color


def _last_trade_timestamp() -> pd.Timestamp | None:
    """Latest quote last-trade timestamp across US and Canadian markets."""
    last_us_timestamp = st.session_state.get("last_us_timestamp")
    last_ca_timestamp = st.session_state.get("last_ca_timestamp")
    return max(
        (ts for ts in (last_us_timestamp, last_ca_timestamp) if ts and not pd.isna(ts)),
        default=None,
    )


def _render_cash_securities_donut(
    cash_balance: float, securities_value: float, hide_balances: bool
) -> go.Figure:
    """Tiny donut showing the cash / securities split."""
    total = cash_balance + securities_value
    securities_pct = securities_value / total if total else 0
    hovertemplate = (
        "%{label}: %{percent}<extra></extra>"
        if hide_balances
        else "%{label}: $%{value:,.2f} CAD<extra></extra>"
    )
    fig = go.Figure(
        go.Pie(
            labels=["Securities", "Cash"],
            values=[securities_value, cash_balance],
            hole=0.7,
            sort=False,
            direction="clockwise",
            marker=dict(colors=[DONUT_SECURITIES_COLOR, DONUT_CASH_COLOR]),
            textinfo="none",
            hovertemplate=hovertemplate,
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
    account_number: str,
    account_type: str,
    account_owner: str,
    portfolio_summary: dict,
    hide_balances: bool,
) -> None:
    """Draw KPIs for the balances of a selected portfolio."""

    def _fmt_amount(amount: float) -> str:
        return MASKED_VALUE if hide_balances else f"${amount:,.2f}"

    with st.container(border=True, horizontal=True, width="stretch"):
        st.metric(
            (
                f"{account_type} {MASKED_VALUE}"
                if hide_balances
                else f"{account_type} #{account_number}"
            ),
            MASKED_VALUE if hide_balances else account_owner,
            border=False,
        )
        unrealized_gain = portfolio_summary["unrealized_gain"]
        return_on_cost = portfolio_summary["return_on_cost"]
        total_value_delta = (
            f"{return_on_cost:+.2%}"
            if hide_balances
            else f"{unrealized_gain:+,.2f}  {return_on_cost:+.2%}"
        )
        pnl_intraday = portfolio_summary["pnl_intraday"]
        prev_securities_value = portfolio_summary["market_value"] - pnl_intraday
        intraday_pct = (
            pnl_intraday / prev_securities_value if prev_securities_value else None
        )
        if hide_balances:
            # Dollar amounts are masked; percentages stay visible
            intraday_delta = (
                f"{intraday_pct:+.2%}" if intraday_pct is not None else MASKED_VALUE
            )
        elif intraday_pct is not None:
            intraday_delta = f"{pnl_intraday:+,.2f}  {intraday_pct:+.2%}"
        else:
            intraday_delta = f"{pnl_intraday:+,.2f}"
        st.metric(
            "Total Value CAD",
            _fmt_amount(portfolio_summary["total_value"]),
            intraday_delta,
            border=False,
        )
        st.metric(
            "Securities Value CAD",
            _fmt_amount(portfolio_summary["market_value"]),
            total_value_delta,
            delta_arrow="off",
            border=False,
        )
        with st.container(border=False):
            st.plotly_chart(
                _render_cash_securities_donut(
                    portfolio_summary["cash_balance"],
                    portfolio_summary["total_value"]
                    - portfolio_summary["cash_balance"],
                    hide_balances,
                ),
                config={"displayModeBar": False},
            )
        st.metric(
            "Cash CAD",
            _fmt_amount(portfolio_summary["cash_balance"]),
            f"{portfolio_summary['cash_pct']:.1%}",
            delta_color="blue",
            delta_arrow="off",
            border=False,
        )
        st.metric(
            "Total Return CAD",
            _fmt_amount(
                portfolio_summary["total_value"] - portfolio_summary["net_investment"]
            ),
            f"{portfolio_summary['mwrr']:+.2%}",
            delta_description="MWRR",
            delta_arrow="off",
            border=False,
        )


def _render_refresh_badge(active_page: str) -> None:
    refreshed = st.session_state.get("last_refresh_by_page", {}).get(active_page)
    if refreshed:
        natural, color = _humanize_timestamp_or_na(refreshed)
        st.badge(f"Refreshed {natural}", color=color, help=str(refreshed))
    else:
        natural, _ = _humanize_timestamp_or_na(_last_trade_timestamp())
        st.badge(f"Last trade {natural}", color="gray")


def render_status_inline(rates: dict, active_page: str) -> None:
    """Rates captions, Auto Refresh toggle, and refresh badge, rendered into
    the caller's horizontal container (for compact page headers)."""
    st.caption(f"USD/CAD: {rates['fx_rate']:.3f}")
    st.caption(f"T-Bill 6m: {rates['rf_rate']:.2%}")
    render_auto_refresh_toggle()
    _render_refresh_badge(active_page)


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
        for i, (symbol, row) in enumerate(df.iterrows()):
            c[i].metric(
                SNAPSHOT_DISPLAY_NAMES.get(symbol, row["name"]),
                value=f"${row['close']:,.2f}",
                delta=f"{row['change_percent']:+.2%}",
                help=row["name"],
                border=True,
                chart_data=row["sparkline"],
                chart_type="line",
                height=HEIGHT_MARKET_SNAPSHOT,
            )


def render_portfolio_kpis(df: pd.DataFrame, hide_balances: bool) -> None:
    """Render the portfolio KPIs."""

    def _fmt_delta(amount: float) -> str:
        return MASKED_VALUE if hide_balances else f"{amount:+,.2f} CAD"

    delta_kwargs = {"delta_color": "off", "delta_arrow": "off"} if hide_balances else {}

    st.metric(
        "Best Intraday",
        f"{df['symbol'][df['intraday_change'].idxmax()]}",
        _fmt_delta(df["intraday_change"].max()),
        **delta_kwargs,
    )
    st.metric(
        "Worst Intraday",
        f"{df['symbol'][df['intraday_change'].idxmin()]}",
        _fmt_delta(df["intraday_change"].min()),
        **delta_kwargs,
    )
    st.metric(
        "Total FX Exposure",
        MASKED_VALUE if hide_balances else f"${df['fx_exposure'].sum():,.2f} CAD",
    )
    st.metric("No. of Holdings", f"{len(df)}")
    st.metric(
        "Average Days Held",
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
