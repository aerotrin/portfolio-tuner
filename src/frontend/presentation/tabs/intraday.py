import pandas as pd
import streamlit as st

from frontend.presentation.settings import MOVER_SHOW_COUNT
from frontend.presentation.styles import (
    POSITIONS_EQUITY_TABLE_CONFIG,
    POSITIONS_OPTION_TABLE_CONFIG,
    QUOTE_TABLE_CONFIG,
    positions_table_styler,
    quote_table_styler,
)
from frontend.presentation.widgets.kpis import (
    render_intraday_health_bar,
    render_portfolio_kpis,
    render_positions_health_bar,
)
from frontend.presentation.widgets.transaction_form import transaction_form
from frontend.presentation.widgets.treemaps import (
    render_treemap_intraday,
    render_treemap_positions,
)
from frontend.shared.config_loader import SymbolGroup


def render_portfolio_positions(
    holdings: pd.DataFrame | None,
    portfolio_summary: dict,
    account_id: str,
    account_name: str,
    fx_rate: float,
) -> None:
    """Intraday view for current account holdings."""

    portfolio_value = portfolio_summary["total_value"]
    cash_balance = portfolio_summary["cash_balance"]

    header = st.columns([0.8, 0.2])
    with header[0]:
        st.markdown("#### :material/table_rows: Positions")
    with header[1]:
        view = st.radio(
            "Select view",
            options=["Intraday", "Holdings"],
            index=0,
            label_visibility="collapsed",
            horizontal=True,
            key="intraday-view-selector",
        )

    if holdings is None:
        st.info("No holdings found")
    else:
        df = holdings.copy()
        equity_df = df[df["holding_category"] == "Equity"]
        option_df = df[df["holding_category"].isin(["Call Option", "Put Option"])]

        # Metrics
        with st.container(border=True, horizontal=True):
            render_portfolio_kpis(holdings)

        # Treemap
        if view == "Intraday":
            fig = render_treemap_intraday(
                holdings, top_label="Intraday", has_weight=True
            )
            st.plotly_chart(fig, key="chart-holdings-securities")

            # Health bar
            render_intraday_health_bar(df)

            # Quote table
            if not equity_df.empty:
                st.markdown("###### Stocks & ETFs")
                st.dataframe(
                    quote_table_styler(equity_df),
                    hide_index=True,
                    column_order=QUOTE_TABLE_CONFIG.keys(),
                    column_config=QUOTE_TABLE_CONFIG,
                    key="table-holdings-quote",
                )
            if not option_df.empty:
                st.markdown("###### Options")
                st.dataframe(
                    quote_table_styler(option_df),
                    hide_index=True,
                    column_order=QUOTE_TABLE_CONFIG.keys(),
                    column_config=QUOTE_TABLE_CONFIG,
                    key="table-holdings-quote",
                )

        else:
            fig = render_treemap_positions(df)
            st.plotly_chart(fig, key="chart-holdings-open")

            # Health bar
            render_positions_health_bar(df)

            # Positions Table
            if not equity_df.empty:
                st.markdown("###### Stocks & ETFs")
                st.dataframe(
                    positions_table_styler(equity_df),
                    hide_index=True,
                    column_order=POSITIONS_EQUITY_TABLE_CONFIG.keys(),
                    column_config=POSITIONS_EQUITY_TABLE_CONFIG,
                    key="table-holdings-open",
                )
            if not option_df.empty:
                st.markdown("###### Options")
                st.dataframe(
                    positions_table_styler(option_df),
                    hide_index=True,
                    column_order=POSITIONS_OPTION_TABLE_CONFIG.keys(),
                    column_config=POSITIONS_OPTION_TABLE_CONFIG,
                    key="table-holdings-open-option-osi",
                )
                st.caption(
                    "⚠️ Option value shown here reflects only intrinsic value (not actual contract price). Market Value and P/L are based on intrinsic value alone. Intraday change for option price is also not supported."
                )

    record_transaction = st.button(
        "Record Transaction", icon=":material/edit:", type="secondary"
    )
    if record_transaction:
        transaction_form(
            account_id,
            account_name,
            df,
            fx_rate,
            portfolio_value,
            cash_balance,
        )


def render_market_intraday(
    market_data: pd.DataFrame,
    market_type: str,
    groups: list[SymbolGroup],
    key_prefix: str,
) -> None:
    """Intraday view for market-wide symbols, grouped by thematic group."""

    t_str = market_type if market_type.isupper() else market_type.title()
    df = market_data.copy()

    st.markdown("#### :material/show_chart: Intraday")

    label = st.segmented_control(
        f"Select {t_str} group",
        [v.label for v in groups],
        default=groups[0].label,
        label_visibility="collapsed",
        key=f"{key_prefix}-intraday-viewer-view-selector",
    )
    group = next((g for g in groups if g.label == label), None)

    if group is None:
        st.info("Please select a group")
        return

    sub = df[df.index.isin(group.symbols)]
    if sub.empty:
        st.info("No symbols found for the selected group")
        return

    fig = render_treemap_intraday(
        sub, top_label=group.label, size_by=None, has_weight=False
    )
    st.plotly_chart(fig, key=f"{key_prefix}-chart-intraday-viewer-{group.label}")

    render_intraday_health_bar(sub)

    st.markdown(f"###### {group.label} {t_str} Quotes")
    st.dataframe(
        quote_table_styler(sub),
        hide_index=True,
        column_order=QUOTE_TABLE_CONFIG.keys(),
        column_config=QUOTE_TABLE_CONFIG,
        key=f"{key_prefix}-table-intraday-viewer-{group.label}-quote",
    )


def render_market_movers(market_data: pd.DataFrame, market_type: str) -> None:
    """Render market movers for a given market_type of security."""
    t_str = market_type if market_type.isupper() else market_type.title()
    df = market_data.copy()

    c = st.columns([5, 1])
    with c[0]:
        st.markdown("#### :material/notifications_active: Market Movers")

    with c[1]:
        market = st.radio(
            "Select market",
            options=["US", "Canada"],
            index=0,
            label_visibility="collapsed",
            horizontal=True,
            key=f"market-movers-selector-{market_type}",
        )
    currency = "CAD" if market == "Canada" else "USD"
    sub_df = df[df["currency"] == currency]
    if sub_df.empty:
        st.info("No symbols found for the selected market")
        return

    volume_df = sub_df.sort_values(by="volume", ascending=False).head(MOVER_SHOW_COUNT)
    up_df = (
        sub_df[sub_df["change_percent"] > 0]
        .sort_values(by="change_percent", ascending=False)
        .head(MOVER_SHOW_COUNT)
    )
    down_df = (
        sub_df[sub_df["change_percent"] < 0]
        .sort_values(by="change_percent", ascending=True)
        .head(MOVER_SHOW_COUNT)
    )

    st.markdown(f"##### :material/swap_horiz: Most Active {t_str}s")
    fig = render_treemap_intraday(volume_df, top_label="Most Active", has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"Most Active {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(volume_df),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
        )

    st.markdown(f"##### :material/arrow_upward: Top {t_str} Gainers ")
    fig = render_treemap_intraday(up_df, top_label="Top Gainers", has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"Top Gainers {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(up_df),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
        )

    st.markdown(f"##### :material/arrow_downward: Top {t_str} Losers ")
    fig = render_treemap_intraday(down_df, top_label="Top Losers", has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"Top Losers {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(down_df),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
        )
