import pandas as pd
import streamlit as st

from frontend.shared.config_loader import SymbolGroup
from frontend.shared.settings import MOVER_SHOW_COUNT
from frontend.shared.styles import QUOTE_TABLE_CONFIG, quote_table_styler
from frontend.widgets.treemaps import render_treemap_intraday


def create_mover_groups(
    quotes: pd.DataFrame,
    base_groups: list[SymbolGroup],
) -> list[SymbolGroup]:
    """Create mover groups (most active, gainers, losers) for CAD and USD currencies."""
    mover_groups = []

    for currency in ["USD", "CAD"]:
        sub_quotes = quotes[quotes["currency"] == currency]
        country = "US" if currency == "USD" else "Canada"

        # Most active (by volume)
        most_active = (
            sub_quotes.sort_values(by="volume", ascending=False)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if most_active:
            mover_groups.append(
                SymbolGroup(
                    label=f"Most Active {country}",
                    symbols=tuple(most_active),
                )
            )

        # Top gainers (by change_percent descending)
        gainers = (
            sub_quotes[sub_quotes["change_percent"] > 0]
            .sort_values(by="change_percent", ascending=False)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if gainers:
            mover_groups.append(
                SymbolGroup(
                    label=f"Top Gainers {country}",
                    symbols=tuple(gainers),
                )
            )

        # Top losers (by change_percent ascending)
        losers = (
            sub_quotes[sub_quotes["change_percent"] < 0]
            .sort_values(by="change_percent", ascending=True)
            .head(MOVER_SHOW_COUNT)
            .index.tolist()
        )
        if losers:
            mover_groups.append(
                SymbolGroup(
                    label=f"Top Losers {country}",
                    symbols=tuple(losers),
                )
            )

    return mover_groups + base_groups


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

    up_df = (
        sub_df[sub_df["change_percent"] > 0]
        .sort_values(by="change_percent", ascending=False)
        .head(MOVER_SHOW_COUNT)
    )
    st.markdown(f"##### :material/arrow_upward: Top {t_str} Gainers ")
    if not up_df.empty:
        fig = render_treemap_intraday(up_df, top_label="Top Gainers", has_weight=False)
        st.plotly_chart(fig)
        with st.expander(f"Top Gainers {t_str} Quote Table", icon=":material/table:"):
            st.dataframe(
                quote_table_styler(up_df),
                hide_index=True,
                column_order=QUOTE_TABLE_CONFIG.keys(),
                column_config=QUOTE_TABLE_CONFIG,
            )
    else:
        st.info("No gainers found for the selected market")

    down_df = (
        sub_df[sub_df["change_percent"] < 0]
        .sort_values(by="change_percent", ascending=True)
        .head(MOVER_SHOW_COUNT)
    )
    st.markdown(f"##### :material/arrow_downward: Top {t_str} Losers ")
    if not down_df.empty:
        fig = render_treemap_intraday(down_df, top_label="Top Losers", has_weight=False)
        st.plotly_chart(fig)
        with st.expander(f"Top Losers {t_str} Quote Table", icon=":material/table:"):
            st.dataframe(
                quote_table_styler(down_df),
                hide_index=True,
                column_order=QUOTE_TABLE_CONFIG.keys(),
                column_config=QUOTE_TABLE_CONFIG,
            )
    else:
        st.info("No losers found for the selected market")
