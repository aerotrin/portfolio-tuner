from typing import cast

import pandas as pd
import streamlit as st

from frontend.shared.styles import (
    POSITIONS_EQUITY_TABLE_CONFIG,
    POSITIONS_OPTION_TABLE_CONFIG,
    QUOTE_TABLE_CONFIG,
    positions_table_styler,
    quote_table_styler,
)
from frontend.widgets.kpis import (
    render_intraday_health_bar,
    render_portfolio_kpis,
    render_positions_health_bar,
)
from frontend.widgets.treemaps import render_treemap_intraday, render_treemap_positions


def render_portfolio_positions(
    holdings: pd.DataFrame | None,
) -> None:
    """Intraday view for current account holdings."""

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
        equity_df = cast(pd.DataFrame, df[df["holding_category"] == "Equity"])
        option_df = cast(
            pd.DataFrame, df[df["holding_category"].isin(["Call Option", "Put Option"])]
        )

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
                    key="table-holdings-quote-stocks",
                )
            if not option_df.empty:
                st.markdown("###### Options")
                st.dataframe(
                    quote_table_styler(option_df),
                    hide_index=True,
                    column_order=QUOTE_TABLE_CONFIG.keys(),
                    column_config=QUOTE_TABLE_CONFIG,
                    key="table-holdings-quote-options",
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
                    key="table-holdings-open-stocks",
                )
            if not option_df.empty:
                st.markdown("###### Options")
                st.dataframe(
                    positions_table_styler(option_df),
                    hide_index=True,
                    column_order=POSITIONS_OPTION_TABLE_CONFIG.keys(),
                    column_config=POSITIONS_OPTION_TABLE_CONFIG,
                    key="table-holdings-open-options",
                )
                st.caption(
                    "⚠️ Option value shown here reflects only intrinsic value (not actual contract price). Market Value and P/L are based on intrinsic value alone. Intraday change for option price is also not supported."
                )
