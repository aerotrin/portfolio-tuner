from typing import cast

import pandas as pd
import streamlit as st

from frontend.shared.styles import QUOTE_TABLE_CONFIG, quote_table_styler
from frontend.shared.symbols_loader import TYPE_ORDER, SymbolGroup, facet_sort_key
from frontend.widgets.kpis import render_intraday_health_bar
from frontend.widgets.treemaps import render_treemap_intraday


def render_market_intraday(
    market_data: pd.DataFrame,
    market_type: str,
    groups: list[SymbolGroup],
    key_prefix: str,
) -> None:
    """Market-map intraday view: one treemap nesting region -> group -> symbol.

    Type pills give a one-click asset-class slice and a group multiselect the
    fine cut (both empty means all, like Performance); region is treemap
    structure rather than a filter — click a region tile to zoom into it.
    """

    t_str = market_type if market_type.isupper() else market_type.title()
    df = market_data.copy()
    df = df.sort_values(by="change_percent", ascending=False)

    st.markdown("#### :material/show_chart: Intraday")

    # Top-to-bottom narrowing needs no state tricks: the multiselect options are
    # computed after the pills value is read in the same run, and Streamlit
    # prunes stored multiselect values that fall outside the narrowed options.
    type_options = sorted(
        {g.type for g in groups}, key=lambda v: facet_sort_key(v, TYPE_ORDER)
    )
    sel_types = []
    if len(type_options) > 1:  # Stocks page is all-Equity — hide a one-chip row
        sel_types = (
            st.pills(
                ":material/category: Type",
                type_options,
                selection_mode="multi",
                key=f"{key_prefix}-intraday-type",
            )
            or []
        )
    typed_groups = [g for g in groups if g.type in set(sel_types or type_options)]

    label_options = list(dict.fromkeys(g.label for g in typed_groups))
    selected = st.multiselect(
        ":material/filter_list: Filter by groups",
        label_options,
        placeholder="All groups",
        key=f"{key_prefix}-intraday-groups",
    )
    chosen = set(selected or label_options)

    # One row per (group, symbol): the treemap shows a symbol once per group it
    # belongs to, each under its own region/group parent.
    frames = []
    for group in typed_groups:
        if group.label not in chosen:
            continue
        part = df.loc[df.index.intersection(group.symbols)]
        if not part.empty:
            frames.append(part.assign(region=group.region, group_label=group.label))

    if not frames:
        st.info("No symbols found for the selected groups")
        return
    sub = pd.concat(frames)

    fig = render_treemap_intraday(
        sub,
        top_label=f"{t_str} Market",
        size_by=None,
        has_weight=False,
        group_cols=["region", "group_label"],
    )
    st.plotly_chart(fig, key=f"{key_prefix}-chart-intraday-viewer")

    # Health bar and table count each security once, however many groups it is in.
    flat = sub[~sub.index.duplicated(keep="first")]
    render_intraday_health_bar(flat)

    st.markdown(f"###### {t_str} Quotes")
    st.dataframe(
        quote_table_styler(flat),
        hide_index=True,
        column_order=QUOTE_TABLE_CONFIG.keys(),
        column_config=QUOTE_TABLE_CONFIG,
        key=f"{key_prefix}-table-intraday-viewer-quote",
    )
    st.caption(f"{len(flat)} securities across {sub['group_label'].nunique()} groups")


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
