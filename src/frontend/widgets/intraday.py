import pandas as pd
import streamlit as st

from frontend.shared.symbols_loader import SymbolGroup
from frontend.shared.styles import QUOTE_TABLE_CONFIG, quote_table_styler
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
