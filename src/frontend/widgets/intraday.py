from typing import cast

import pandas as pd
import streamlit as st

from frontend.shared.styles import QUOTE_TABLE_CONFIG, quote_table_styler
from frontend.shared.symbols_loader import SymbolGroup
from frontend.widgets.kpis import render_intraday_health_bar
from frontend.widgets.treemaps import render_treemap_intraday


def render_market_intraday(
    market_data: pd.DataFrame,
    market_type: str,
    groups: list[SymbolGroup],
    key_prefix: str,
) -> None:
    """Intraday view for market-wide symbols, grouped by thematic group."""

    t_str = market_type if market_type.isupper() else market_type.title()
    df = market_data.copy()
    df = df.sort_values(by="change_percent", ascending=False)

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


def render_portfolio_intraday(
    portfolio: pd.DataFrame | None,
) -> None:
    """Intraday view for current account holdings."""

    st.markdown("#### :material/show_chart: Intraday")

    if portfolio is None:
        st.info("No holdings found")
    else:
        df = portfolio.copy()
        df = df.sort_values(by="change_percent", ascending=False)
        equity_df = cast(pd.DataFrame, df[df["holding_category"] == "Equity"])
        option_df = cast(
            pd.DataFrame, df[df["holding_category"].isin(["Call Option", "Put Option"])]
        )

        # Treemap
        fig = render_treemap_intraday(portfolio, top_label="Portfolio", has_weight=True)
        st.plotly_chart(fig, key="chart-holdings-intraday")

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
                key="table-holdings-intraday-quote-stocks",
            )
        if not option_df.empty:
            st.markdown("###### Options")
            st.dataframe(
                quote_table_styler(option_df),
                hide_index=True,
                column_order=QUOTE_TABLE_CONFIG.keys(),
                column_config=QUOTE_TABLE_CONFIG,
                key="table-holdings-intraday-quote-options",
            )
