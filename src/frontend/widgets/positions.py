from typing import cast

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
import pandas as pd
import streamlit as st


def render_portfolio_positions(
    holdings: pd.DataFrame | None,
) -> None:
    """Intraday view for current account holdings."""

    st.markdown("#### :material/table_rows: Positions")

    if holdings is None:
        st.info("No holdings found")
    else:
        df = holdings.copy()
        df = df.sort_values(by="gain_pct", ascending=False)
        equity_df = cast(pd.DataFrame, df[df["holding_category"] == "Equity"])
        option_df = cast(
            pd.DataFrame, df[df["holding_category"].isin(["Call Option", "Put Option"])]
        )

        # Metrics
        with st.container(border=True, horizontal=True):
            render_portfolio_kpis(holdings)

        # Treemap
        c = st.columns(2)
        with c[0]:
            fig = render_treemap_intraday(
                holdings, top_label="Intraday", has_weight=True, row_px=275
            )
            st.plotly_chart(fig, key="chart-holdings-intraday")
            # Health bar
            render_intraday_health_bar(df)

        with c[1]:
            fig = render_treemap_positions(df, row_px=275)
            st.plotly_chart(fig, key="chart-holdings-open")

            # Health bar
            render_positions_health_bar(df)

        with st.expander("Intraday Quotes"):
            # Quote table — sorted by intraday change
            intraday_equity_df = equity_df.sort_values(by="change_percent", ascending=False)
            intraday_option_df = option_df.sort_values(by="change_percent", ascending=False)
            if not intraday_equity_df.empty:
                st.markdown("###### Stocks & ETFs")
                st.dataframe(
                    quote_table_styler(intraday_equity_df),
                    hide_index=True,
                    column_order=QUOTE_TABLE_CONFIG.keys(),
                    column_config=QUOTE_TABLE_CONFIG,
                    key="table-holdings-intraday-quote-stocks",
                )
            if not intraday_option_df.empty:
                st.markdown("###### Options")
                st.dataframe(
                    quote_table_styler(intraday_option_df),
                    hide_index=True,
                    column_order=QUOTE_TABLE_CONFIG.keys(),
                    column_config=QUOTE_TABLE_CONFIG,
                    key="table-holdings-intraday-quote-options",
                )

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
