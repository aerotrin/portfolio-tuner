from functools import partial

import pandas as pd
import streamlit as st

from frontend.shared.styles import QUOTE_TABLE_CONFIG, quote_table_styler
from frontend.shared.symbols_loader import TYPE_ORDER, SymbolGroup, facet_sort_key
from frontend.widgets.filters import sync_facets_to_drill
from frontend.widgets.kpis import render_intraday_health_bar
from frontend.widgets.treemaps import (
    CHANGE_COLOR_MAX,
    COLOR_CHANGE,
    COLOR_REL_VOLUME,
    REL_VOLUME_COLOR_MAX,
    format_cap,
    leaf_labels,
    render_treemap_intraday,
)

DRILL_COLS = ["region", "group_label"]
METRIC_LABELS = {COLOR_CHANGE: "Change %", COLOR_REL_VOLUME: "Rel. volume"}
SORT_DOLLAR_VOLUME = "dollar_volume"
SORT_LABELS = {COLOR_CHANGE: "Change %", SORT_DOLLAR_VOLUME: "Dollar volume"}


def _sort_quotes(df: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    """Highest first, securities without the metric last. Tiles are equal
    sized, so this row order is the tile order within each group."""
    if sort_by not in df.columns:
        sort_by = COLOR_CHANGE
    return df.sort_values(
        by=sort_by, ascending=False, na_position="last", kind="stable"
    )


def _tile_ids(sub: pd.DataFrame, top_label: str) -> tuple[list, list]:
    """Per-row label and treemap id at each depth below the root (region,
    group, symbol). Ids mirror Plotly's "root/region/group/symbol" paths and
    are compared whole rather than split on "/", since group labels may
    contain a slash."""
    parts = [
        pd.Series(part, index=sub.index).astype(str)
        for part in (*(sub[col] for col in DRILL_COLS), leaf_labels(sub))
    ]
    level_id = pd.Series(top_label, index=sub.index, dtype="object")
    level_ids = []
    for part in parts:
        level_id = level_id + "/" + part
        level_ids.append(level_id)
    return parts, level_ids


def _next_level(
    sub: pd.DataFrame, top_label: str, level: str | None, clicked: str | None
) -> str | None:
    """Treemap level after a click, given the level it was zoomed to.

    Plotly zooms into whichever tile is clicked, except that clicking the
    tile already zoomed into walks back up to its parent. The click event
    carries only the tile, not the direction, so the level is tracked in
    session state and the figure is drawn at it. None means the root.
    """
    if not clicked or clicked == top_label:
        return None
    if clicked != level:
        return clicked
    _, level_ids = _tile_ids(sub, top_label)
    for depth, ids in enumerate(level_ids):
        hit = ids == clicked
        if hit.any():
            return level_ids[depth - 1][hit].iloc[0] if depth else None
    return None


def _drill_filter(
    sub: pd.DataFrame, top_label: str, level: str | None
) -> tuple[pd.DataFrame, list[str]]:
    """Rows under the treemap tile zoomed into, plus its path below the root.
    Everything and an empty path for the root or a tile no longer on the map.
    """
    if not level:
        return sub, []
    parts, level_ids = _tile_ids(sub, top_label)
    for depth, ids in enumerate(level_ids):
        hit = ids == level
        if hit.any():
            first = hit.to_numpy().argmax()
            return sub[hit], [part.iloc[first] for part in parts[: depth + 1]]
    return sub, []


def _record_click(chart_key: str) -> None:
    """Keep the clicked tile for the next run. The chart's own selection
    cannot carry it: live tile text changes the figure, and a changed figure
    remounts the chart with an empty selection."""
    points = st.session_state[chart_key]["selection"]["points"]
    if points:
        st.session_state[f"{chart_key}-click"] = points[0].get("id")


def _reset_drill(chart_key: str) -> None:
    """A filter change redraws the treemap at its root, so drop the stored
    zoom level — otherwise the table would stay on a level the map left."""
    for key in (chart_key, f"{chart_key}-level", f"{chart_key}-click"):
        st.session_state.pop(key, None)


def _quotes_heading(base: str, sel_types: list[str], drill_path: str) -> str:
    """e.g. "ETF Quotes (Fixed Income) · US / Core"."""
    heading = f"{base} ({', '.join(sel_types)})" if sel_types else base
    return f"{heading} · {drill_path}" if drill_path else heading


def render_market_intraday(
    market_data: pd.DataFrame,
    market_type: str,
    groups: list[SymbolGroup],
    key_prefix: str,
) -> None:
    """Market-map intraday view: one treemap nesting region -> group -> symbol.

    Type pills give a one-click asset-class slice (none selected means all);
    region and group are treemap structure — clicking a region, group or
    symbol tile zooms into it and narrows the health bar and quote table to
    match. The Performance tab's filter follows the same view.
    """

    t_str = market_type if market_type.isupper() else market_type.title()
    df = market_data.copy()

    st.markdown("#### :material/show_chart: Intraday")
    chart_key = f"{key_prefix}-chart-intraday-viewer"

    type_options = sorted(
        {g.type for g in groups}, key=lambda v: facet_sort_key(v, TYPE_ORDER)
    )
    sel_types = []
    color_by = COLOR_CHANGE
    sort_by = COLOR_CHANGE
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        if len(type_options) > 1:  # Stocks page is all-Equity — hide a one-chip row
            sel_types = (
                st.pills(
                    ":material/category: Type",
                    type_options,
                    selection_mode="multi",
                    key=f"{key_prefix}-intraday-type",
                    on_change=_reset_drill,
                    args=(chart_key,),
                )
                or []
            )
        # Snapshots cached before a metric existed do not carry it
        if COLOR_REL_VOLUME in df.columns:
            color_by = (
                st.segmented_control(
                    ":material/palette: Colour",
                    list(METRIC_LABELS),
                    format_func=METRIC_LABELS.__getitem__,
                    default=COLOR_CHANGE,
                    key=f"{key_prefix}-intraday-color",
                    width="content",
                )
                or COLOR_CHANGE
            )
        if SORT_DOLLAR_VOLUME in df.columns:
            sort_by = (
                st.segmented_control(
                    ":material/sort: Sort",
                    list(SORT_LABELS),
                    format_func=SORT_LABELS.__getitem__,
                    default=COLOR_CHANGE,
                    key=f"{key_prefix}-intraday-sort",
                    help="Orders the symbols inside each group, highest first. "
                    "Dollar volume: today's volume × price, in the security's "
                    "own currency.",
                    width="content",
                )
                or COLOR_CHANGE
            )
    df = _sort_quotes(df, sort_by)
    typed_groups = [g for g in groups if g.type in set(sel_types or type_options)]

    # One row per (group, symbol): the treemap shows a symbol once per group it
    # belongs to, each under its own region/group parent.
    frames = []
    for group in typed_groups:
        part = df.loc[df.index.intersection(group.symbols)]
        if not part.empty:
            frames.append(part.assign(region=group.region, group_label=group.label))

    if not frames:
        st.info("No symbols found for the selected types")
        return
    sub = pd.concat(frames)

    top_label = f"{t_str} Market"
    level_key = f"{chart_key}-level"
    level = st.session_state.get(level_key)
    clicked = st.session_state.pop(f"{chart_key}-click", None)
    if clicked:
        level = _next_level(sub, top_label, level, clicked)
    drilled, drill_parts = _drill_filter(sub, top_label, level)
    if not drill_parts:
        level = None
    st.session_state[level_key] = level
    sync_facets_to_drill(key_prefix, sel_types, drill_parts)

    fig = render_treemap_intraday(
        sub,
        top_label=top_label,
        size_by=None,
        has_weight=False,
        group_cols=DRILL_COLS,
        color_by=color_by,
    )
    # Drawn at the tracked level, so the zoom survives a chart remount.
    fig.update_traces(level=level)
    st.plotly_chart(
        fig,
        on_select=partial(_record_click, chart_key),
        selection_mode="points",
        key=chart_key,
    )
    sub = drilled
    drill_path = " / ".join(drill_parts)

    # Health bar and table count each security once, however many groups it is in.
    flat = sub[~sub.index.duplicated(keep="first")]
    render_intraday_health_bar(flat, show_squares=False)
    if color_by == COLOR_REL_VOLUME:
        st.caption(
            "Colour: today's volume ÷ 20-day average, darkest at "
            f"{REL_VOLUME_COLOR_MAX:.0f}× or more. Reads low early in the session."
        )
    else:
        st.caption(
            "Colour: day change, full red or green at "
            f"±{format_cap(CHANGE_COLOR_MAX)} or more."
        )

    heading = _quotes_heading(f"{t_str} Quotes", sel_types, drill_path)
    st.markdown(f"###### {heading}")
    st.dataframe(
        quote_table_styler(flat),
        hide_index=True,
        height="content",
        column_order=QUOTE_TABLE_CONFIG.keys(),
        column_config=QUOTE_TABLE_CONFIG,
        key=f"{key_prefix}-table-intraday-viewer-quote",
    )
    if drill_path:
        st.caption(f"{len(flat)} securities")
    else:
        st.caption(
            f"{len(flat)} securities across {sub['group_label'].nunique()} groups"
        )
