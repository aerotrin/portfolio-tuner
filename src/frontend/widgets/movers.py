import pandas as pd
import streamlit as st

from frontend.shared.settings import MOVER_SHOW_COUNT
from frontend.shared.styles import QUOTE_TABLE_CONFIG, quote_table_styler
from frontend.widgets.treemaps import render_treemap_intraday

MOST_ACTIVE = "Most Active"
UNUSUAL_VOLUME = "Unusual Volume"


def _has_relative_volume(df: pd.DataFrame) -> bool:
    return "relative_volume" in df.columns and bool(df["relative_volume"].notna().any())


def _volume_leaders(df: pd.DataFrame, count: int, mode: str) -> pd.DataFrame:
    """Top securities by raw volume (Most Active) or by relative volume —
    today's volume ÷ own average — which surfaces unusual trading instead of
    the same large names every day."""
    if mode == UNUSUAL_VOLUME and _has_relative_volume(df):
        ranked = df.dropna(subset=["relative_volume"]).sort_values(
            by="relative_volume", ascending=False
        )
        return ranked.head(count)
    return df.sort_values(by="volume", ascending=False).head(count)


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

    # Data cached before relative volume existed can only rank by raw volume
    volume_title = MOST_ACTIVE
    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        heading = st.empty()
        if _has_relative_volume(sub_df):
            volume_title = (
                st.segmented_control(
                    "Volume ranking",
                    [MOST_ACTIVE, UNUSUAL_VOLUME],
                    default=UNUSUAL_VOLUME,
                    required=True,
                    label_visibility="collapsed",
                    help="Most Active: highest volume. Unusual Volume: highest "
                    "volume relative to the security's own 20-day average.",
                    key=f"market-movers-volume-mode-{market_type}",
                    width="content",
                )
                or UNUSUAL_VOLUME
            )
        heading.markdown(f"##### :material/swap_horiz: {volume_title} {t_str}s")
    volume_df = _volume_leaders(sub_df, MOVER_SHOW_COUNT, volume_title)
    fig = render_treemap_intraday(volume_df, top_label=volume_title, has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"{volume_title} {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(volume_df),
            hide_index=True,
            height="content",
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
                height="content",
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
                height="content",
                column_order=QUOTE_TABLE_CONFIG.keys(),
                column_config=QUOTE_TABLE_CONFIG,
            )
    else:
        st.info("No losers found for the selected market")
