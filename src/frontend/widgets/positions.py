from typing import Any, cast

from frontend.shared.accounts import FIXED_INCOME
from frontend.shared.settings import HEIGHT_POSITIONS_TREEMAP_ROW, MASKED_VALUE
from frontend.shared.styles import (
    POSITIONS_CASH_TABLE_CONFIG,
    POSITIONS_EQUITY_TABLE_CONFIG,
    POSITIONS_FIXED_INCOME_TABLE_CONFIG,
    POSITIONS_OPTION_TABLE_CONFIG,
    QUOTE_TABLE_CONFIG,
    balance_safe_column_order,
    cash_table_styler,
    positions_table_styler,
    quote_table_styler,
    with_account_column,
)
from frontend.widgets.kpis import (
    render_intraday_health_bar,
    render_portfolio_kpis,
    render_positions_health_bar,
)
from frontend.widgets.treemaps import render_treemap_intraday, render_treemap_positions
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

HEIGHT_CASH_DONUT = 160


def _cash_by_account_donut(df: pd.DataFrame, hide_balances: bool) -> go.Figure:
    """Donut of each account's share of total (positive) cash."""
    hovertemplate = (
        "%{label}: %{percent}<extra></extra>"
        if hide_balances
        else "%{label}: $%{value:,.2f} CAD (%{percent})<extra></extra>"
    )
    total = df["cash_balance"].sum()
    fig = go.Figure(
        go.Pie(
            labels=df["label"],
            values=df["cash_balance"],
            hole=0.6,
            sort=False,
            direction="clockwise",
            textinfo="percent",
            textposition="inside",
            hovertemplate=hovertemplate,
        )
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="v", yanchor="middle", y=0.5, x=1.02, xanchor="left"),
        margin=dict(t=0, b=0, l=0, r=0),
        height=HEIGHT_CASH_DONUT,
        annotations=[
            dict(
                text="Cash<br>" + (MASKED_VALUE if hide_balances else f"${total:,.0f}"),
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


def _render_cash_section(
    cash_accounts: list[dict[str, Any]],
    portfolio_total_value: float,
    hide_balances: bool,
) -> None:
    """Per-account cash table, plus a Cash by Account donut when cash is
    spread across several accounts."""
    if not cash_accounts:
        return

    df = pd.DataFrame.from_records(cash_accounts)
    total_values = df["total_value"].where(df["total_value"] != 0)
    df["account_cash_pct"] = (df["cash_balance"] / total_values).fillna(0.0)
    df["weight"] = (
        df["cash_balance"] / portfolio_total_value if portfolio_total_value else 0.0
    )
    df = df.sort_values(by="cash_balance", ascending=False)

    positive = cast(pd.DataFrame, df[df["cash_balance"] > 0])
    show_donut = len(positive) > 1

    st.markdown("###### Cash")
    table_col, donut_col = (
        st.columns([2, 1], vertical_alignment="top")
        if show_donut
        else (st.container(), None)
    )
    with table_col:
        st.dataframe(
            cash_table_styler(df),
            hide_index=True,
            height="content",
            column_order=balance_safe_column_order(
                POSITIONS_CASH_TABLE_CONFIG, hide_balances
            ),
            column_config=POSITIONS_CASH_TABLE_CONFIG,
            key="table-holdings-cash",
        )
        if len(df) > 1:
            total_cash = df["cash_balance"].sum()
            total_pct = (
                total_cash / portfolio_total_value if portfolio_total_value else 0.0
            )
            amount = MASKED_VALUE if hide_balances else f"${total_cash:,.2f} CAD"
            st.caption(f"Total cash {amount} · {total_pct:.1%} of portfolio")
    if donut_col is not None:
        with donut_col:
            st.plotly_chart(
                _cash_by_account_donut(positive, hide_balances),
                config={"displayModeBar": False},
                key="chart-holdings-cash-by-account",
            )


def _render_fixed_income_section(
    df: pd.DataFrame, hide_balances: bool, has_accounts: bool
) -> None:
    """GICs and term deposits, valued from their terms instead of a quote."""
    df = df.sort_values(by="fi_days_to_maturity", na_position="last").copy()
    for col in ("fi_issue_date", "fi_maturity_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    config = POSITIONS_FIXED_INCOME_TABLE_CONFIG
    if has_accounts:
        config = with_account_column(config, "name")

    st.markdown("###### Fixed Income")
    matured = df.loc[df["fi_status"] == "Matured", "name"].tolist()
    if matured:
        st.warning(
            "Matured: "
            + ", ".join(matured)
            + ". It stays here at its final value until its redemption is "
            "recorded with **Manage GIC / Term Deposit** in the sidebar.",
            icon=":material/event_available:",
        )
    st.dataframe(
        positions_table_styler(df),
        hide_index=True,
        height="content",
        column_order=balance_safe_column_order(config, hide_balances),
        column_config=config,
        key="table-holdings-open-fixed-income",
    )
    st.caption(
        "Value is principal plus interest accrued to date. Fixed income has no "
        "market price: it counts in the portfolio totals, shows in the Intraday "
        "treemap without a price move, and is left out of the intraday "
        "statistics, correlation and optimization. To record a redemption "
        "or an interest payment, use **Manage GIC / Term Deposit** in the sidebar."
    )


def render_portfolio_positions(
    holdings: pd.DataFrame | None,
    hide_balances: bool,
    cash_accounts: list[dict[str, Any]] | None = None,
    portfolio_total_value: float = 0.0,
) -> None:
    """Intraday view for current account holdings."""

    st.markdown("#### :material/table_rows: Positions")

    if holdings is None:
        if cash_accounts:
            st.markdown("##### Holdings")
            _render_cash_section(cash_accounts, portfolio_total_value, hide_balances)
        st.info("No holdings found")
    else:
        df = holdings.copy()

        # Multi-account frames (all-accounts scope) get an Account column and
        # account-nested treemaps; single-account frames carry one value and
        # render as before. Scope switching lives in the page-level selector.
        has_accounts = "account" in df.columns and df["account"].nunique() > 1
        group_cols = None
        equity_config = POSITIONS_EQUITY_TABLE_CONFIG
        option_config = POSITIONS_OPTION_TABLE_CONFIG
        quote_config = QUOTE_TABLE_CONFIG
        if has_accounts:
            group_cols = ["account"]
            equity_config = with_account_column(POSITIONS_EQUITY_TABLE_CONFIG, "symbol")
            option_config = with_account_column(
                POSITIONS_OPTION_TABLE_CONFIG, "option_osi"
            )
            quote_config = with_account_column(QUOTE_TABLE_CONFIG, "symbol")

        df = df.sort_values(by="gain_pct", ascending=False)
        equity_df = cast(pd.DataFrame, df[df["holding_category"] == "Equity"])
        option_df = cast(
            pd.DataFrame, df[df["holding_category"].isin(["Call Option", "Put Option"])]
        )
        fixed_income_df = cast(pd.DataFrame, df[df["holding_category"] == FIXED_INCOME])
        market_df = cast(pd.DataFrame, df[df["holding_category"] != FIXED_INCOME])

        # Metrics
        with st.container(border=False, horizontal=True):
            render_portfolio_kpis(df, hide_balances)

        # Treemap
        view = st.segmented_control(
            "Treemap view",
            ["Intraday", "Total Return"],
            default="Intraday",
            key="positions_treemap_view",
            label_visibility="collapsed",
        )
        if view == "Total Return":
            fig = render_treemap_positions(
                df,
                row_px=HEIGHT_POSITIONS_TREEMAP_ROW,
                hide_balances=hide_balances,
                group_cols=group_cols,
            )
            st.plotly_chart(fig, key="chart-holdings-open")
            render_positions_health_bar(df)
        else:
            # Same tiles as Total Return, so the layout holds across the toggle;
            # fixed income shows as a neutral tile and stays out of the bar
            fig = render_treemap_intraday(
                df,
                top_label="Intraday",
                has_weight=True,
                row_px=HEIGHT_POSITIONS_TREEMAP_ROW,
                hide_balances=hide_balances,
                group_cols=group_cols,
            )
            st.plotly_chart(fig, key="chart-holdings-intraday")
            render_intraday_health_bar(market_df, unpriced=len(fixed_income_df))

        # Positions Table
        st.markdown("##### Holdings")
        _render_cash_section(cash_accounts or [], portfolio_total_value, hide_balances)
        if not equity_df.empty:
            st.markdown("###### Stocks & ETFs")
            st.dataframe(
                positions_table_styler(equity_df),
                hide_index=True,
                column_order=balance_safe_column_order(equity_config, hide_balances),
                column_config=equity_config,
                height="content",
                key="table-holdings-open-stocks",
            )
        if not option_df.empty:
            st.markdown("###### Options")
            st.dataframe(
                positions_table_styler(option_df),
                hide_index=True,
                height="content",
                column_order=balance_safe_column_order(option_config, hide_balances),
                column_config=option_config,
                key="table-holdings-open-options",
            )
            st.caption(
                "⚠️ Option value shown here reflects only intrinsic value (not actual contract price). Market Value and P/L are based on intrinsic value alone. Intraday change for option price is also not supported."
            )
        if not fixed_income_df.empty:
            _render_fixed_income_section(fixed_income_df, hide_balances, has_accounts)

        with st.expander("Intraday Quote Table", icon=":material/table:"):
            intraday_equity_df = equity_df.sort_values(
                by="change_percent", ascending=False
            )
            intraday_option_df = option_df.sort_values(
                by="change_percent", ascending=False
            )
            if not intraday_equity_df.empty:
                st.markdown("###### Stocks & ETFs")
                st.dataframe(
                    quote_table_styler(intraday_equity_df),
                    hide_index=True,
                    height="content",
                    column_order=quote_config.keys(),
                    column_config=quote_config,
                    key="table-holdings-intraday-quote-stocks",
                )
            if not intraday_option_df.empty:
                st.markdown("###### Options")
                st.dataframe(
                    quote_table_styler(intraday_option_df),
                    hide_index=True,
                    height="content",
                    column_order=quote_config.keys(),
                    column_config=quote_config,
                    key="table-holdings-intraday-quote-options",
                )
