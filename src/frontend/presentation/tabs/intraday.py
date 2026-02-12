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
from frontend.presentation.widgets.allocation_charts import (
    render_portfolio_allocation,
)
from frontend.presentation.widgets.kpis import (
    render_health_bar,
    render_portfolio_kpis,
)
from frontend.presentation.widgets.transaction_form import transaction_form
from frontend.presentation.widgets.treemaps import (
    render_treemap_intraday,
    render_treemap_positions,
)
from frontend.shared.config_loader import SymbolGroup


def _render_transaction_button(
    account_id: str,
    account_name: str,
    holdings: pd.DataFrame | None,
    fx_rate: float,
) -> None:
    record_transaction = st.button(
        "Record Transaction", icon=":material/edit:", type="secondary"
    )
    if record_transaction:
        transaction_form(
            account_id,
            account_name,
            holdings,
            fx_rate,
        )


def render_portfolio_intraday(
    holdings: pd.DataFrame | None,
    account_id: str,
    account_name: str,
    fx_rate: float,
) -> None:
    """Intraday view for current account holdings."""
    st.markdown("#### :material/show_chart: Intraday")

    if holdings is None:
        st.info("No holdings found")
        _render_transaction_button(account_id, account_name, holdings, fx_rate)
        return

    fig = render_treemap_intraday(holdings, top_label="Holdings", has_weight=False)
    st.plotly_chart(fig, key="chart-holdings-securities")
    # st.caption("Size is based on weight in portfolio")
    with st.expander("Holdings Quote Table", icon=":material/table:", expanded=False):
        st.dataframe(
            quote_table_styler(holdings),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
            key="table-holdings-quote",
        )

    st.divider()

    st.markdown("#### :material/table_rows: Positions")

    # Metrics
    with st.container(border=True, horizontal=True):
        render_portfolio_kpis(holdings)

    # Treemap
    fig = render_treemap_positions(holdings)
    st.plotly_chart(fig, key="chart-holdings-open")

    _render_transaction_button(account_id, account_name, holdings, fx_rate)

    # Health bar
    render_health_bar(holdings)

    # Table
    equity_df = holdings[holdings["holding_category"] == "Equity"]
    if not equity_df.empty:
        st.markdown("###### Stocks & ETFs")
        st.dataframe(
            positions_table_styler(equity_df),
            hide_index=True,
            column_order=POSITIONS_EQUITY_TABLE_CONFIG.keys(),
            column_config=POSITIONS_EQUITY_TABLE_CONFIG,
            key="table-holdings-open",
        )

    option_df = holdings[
        holdings["holding_category"].isin(["Call Option", "Put Option"])
    ]

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

    st.divider()

    render_portfolio_allocation(holdings)


def render_market_intraday(
    market_intraday: pd.DataFrame, groups: list[SymbolGroup], type: str, key_prefix: str
) -> None:
    """Intraday view for market-wide symbols, grouped by thematic group."""

    df = market_intraday.copy()

    t_str = type if type.isupper() else type.title()

    st.markdown(f"#### :material/show_chart: {t_str} Intraday")

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

    with st.expander(
        f"{group.label} {t_str} Quote Table",
        icon=":material/table:",
    ):
        st.dataframe(
            quote_table_styler(sub),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
            key=f"{key_prefix}-table-intraday-viewer-{group.label}-quote",
        )

    st.divider()

    c = st.columns([7, 1])
    with c[0]:
        st.markdown(f"#### :material/notifications_active: {t_str} Market Movers")

    with c[1]:
        market = st.segmented_control(
            "Select market",
            ["US", "Canada"],
            default="US",
            label_visibility="collapsed",
            key=f"market-movers-selector-{type}",
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
