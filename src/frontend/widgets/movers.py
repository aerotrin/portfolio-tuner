import pandas as pd
import streamlit as st

from frontend.settings import MOVER_SHOW_COUNT
from frontend.shared.styles import (
    drop_empty_columns,
    QUOTE_TABLE_CONFIG,
    quote_table_styler,
    with_symbol_links,
)
from frontend.widgets.price_chart import symbol_click_kwargs
from frontend.widgets.treemaps import render_treemap_intraday

MOST_ACTIVE = "Most Active"
MARKET_CURRENCIES = {"US": "USD", "Canada": "CAD"}


def _markets_present(df: pd.DataFrame) -> list[str]:
    """Markets with at least one security on the page."""
    currencies = set(df["currency"].dropna())
    return [m for m, currency in MARKET_CURRENCIES.items() if currency in currencies]


def _remember_market(state_key: str, widget_key: str) -> None:
    """A widget's own value is dropped when its page is left, so the choice
    is kept in a plain session key that seeds the control on return."""
    st.session_state[state_key] = st.session_state[widget_key]


def _volume_leaders(df: pd.DataFrame, count: int) -> pd.DataFrame:
    """Top securities by dollar volume (volume x price), which ranks by money
    traded rather than share count. Data cached before the metric existed
    ranks by raw volume."""
    has_dollar_volume = (
        "dollar_volume" in df.columns and df["dollar_volume"].notna().any()
    )
    by = "dollar_volume" if has_dollar_volume else "volume"
    return df.sort_values(by=by, ascending=False, na_position="last").head(count)


def _render_quote_table(df: pd.DataFrame, key: str) -> None:
    styler, config = with_symbol_links(quote_table_styler(df), QUOTE_TABLE_CONFIG)
    st.dataframe(
        styler,
        hide_index=True,
        height="content",
        column_order=drop_empty_columns(QUOTE_TABLE_CONFIG, df),
        column_config=config,
        **symbol_click_kwargs(key, df["symbol"].tolist()),
    )


def render_market_movers(market_data: pd.DataFrame, market_type: str) -> None:
    """Render market movers for a given market_type of security."""
    t_str = market_type if market_type.isupper() else market_type.title()
    df = market_data.copy()

    markets = _markets_present(df)
    market = markets[0] if markets else None
    # Keyed for the CSS in app.py that lines the selector up with the heading
    with st.container(horizontal=True, key="market-movers-heading"):
        st.markdown(
            "#### :material/notifications_active: Market Movers", width="content"
        )
        if len(markets) > 1:
            state_key = f"market-movers-market-{market_type}"
            widget_key = f"{state_key}-control"
            saved = st.session_state.get(state_key)
            market = (
                st.segmented_control(
                    "Market",
                    markets,
                    default=saved if saved in markets else markets[0],
                    required=True,
                    label_visibility="collapsed",
                    key=widget_key,
                    on_change=_remember_market,
                    args=(state_key, widget_key),
                    width="content",
                )
                or markets[0]
            )
    if market is None:
        st.info("No US or Canadian symbols found")
        return
    sub_df = df[df["currency"] == MARKET_CURRENCIES[market]]

    st.markdown(
        f"##### :material/swap_horiz: {MOST_ACTIVE} {t_str}s",
        help="Ranked by dollar volume: today's volume × price.",
    )
    volume_df = _volume_leaders(sub_df, MOVER_SHOW_COUNT)
    fig = render_treemap_intraday(volume_df, top_label=MOST_ACTIVE, has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"{MOST_ACTIVE} {t_str} Quote Table", icon=":material/table:"):
        _render_quote_table(volume_df, f"table-movers-{market_type}-active")

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
            _render_quote_table(up_df, f"table-movers-{market_type}-gainers")
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
            _render_quote_table(down_df, f"table-movers-{market_type}-losers")
    else:
        st.info("No losers found for the selected market")
