import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from frontend.shared.settings import HEIGHT_TREEMAP, MASKED_VALUE
from frontend.shared.time import humanize_timestamp


def _size_treemap(
    elements: int, per_row: int = 12, row_px: int = HEIGHT_TREEMAP, base_px: int = 0
) -> int:
    """Dynamically adjust height based on number of elements."""
    rows = (elements + per_row - 1) // per_row
    rows = max(1, rows)
    return base_px + rows * row_px


def render_treemap_intraday(
    df: pd.DataFrame,
    top_label: str = "",
    size_by: str | None = None,
    has_weight: bool = False,
    row_px=None,
    hide_balances: bool = False,
    group_cols: list[str] | None = None,
) -> go.Figure:
    """Intraday treemap; `group_cols` nests symbols under those columns
    (e.g. region -> group). A symbol appearing in several groups renders once
    per parent. Height is capped when grouped — tiles shrink, not the page."""
    df = df.copy()

    if group_cols:
        n_parents = df.groupby(group_cols, sort=False).ngroups
        height = _size_treemap(df.index.nunique()) + 24 * n_parents
        height = min(max(height, 3 * HEIGHT_TREEMAP), 6 * HEIGHT_TREEMAP)
    else:
        height = (
            _size_treemap(df.shape[0], row_px=row_px)
            if row_px is not None
            else _size_treemap(df.shape[0])
        )

    df["display_text"] = (
        df["close"].map("{:,.2f}".format)
        + " "
        + df["currency"]
        + "<br>"
        + df["change"].map("{:+,.2f}".format)
        + " "
        + df["change_percent"].map("{:.2%}".format)
        + "<br>"
        + df["volume"].map("Vol. {:,.0f}".format)
        + "<br>"
        + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
    )

    path: list = [px.Constant(top_label)]
    if group_cols:
        # An explicit leaf column: passing df.index alongside other path columns
        # is ambiguous to plotly when a column shares the index's name ("symbol").
        df["_leaf"] = df.index
        path.extend([*group_cols, "_leaf"])
    else:
        path.append(df.index)

    base_config = {
        "data_frame": df,
        "path": path,
        "color": "change_percent",
        "color_continuous_scale": "RdYlGn",
        "color_continuous_midpoint": 0,
        "custom_data": ["display_text"],
        "hover_data": ["name", "timestamp"],
    }

    if has_weight:
        base_config["values"] = "weight"
        base_config["hover_data"] = (
            ["name", "timestamp"]
            if hide_balances
            else ["name", "market_value", "timestamp"]
        )

    if size_by is not None and size_by in df.columns:
        base_config["values"] = size_by

    fig = px.treemap(**base_config)

    fig.update_traces(
        textinfo="label+text",
        texttemplate="<b>%{label}</b><br>%{customdata[0]}",
    )

    fig.update_coloraxes(showscale=False)

    fig.update_layout(
        height=height,
        margin=dict(t=0, b=0, l=0, r=0),
    )

    return fig


def render_treemap_positions(
    df: pd.DataFrame, row_px=None, hide_balances: bool = False
) -> go.Figure:
    df = df.copy()

    height = (
        _size_treemap(df.shape[0], row_px=row_px)
        if row_px is not None
        else _size_treemap(df.shape[0])
    )

    option_df = df[df["holding_category"].isin(["Call Option", "Put Option"])]
    stocks_df = df[~df["holding_category"].isin(["Call Option", "Put Option"])]

    if hide_balances:
        common_text = (
            MASKED_VALUE + "<br>" + df["gain_pct"].map("{:+.2%}".format) + "<br>"
        )
        stocks_qty_text = ""
        option_qty_text = ""
    else:
        common_text = (
            df["market_value"].map("{:,.2f} CAD".format)
            + "<br>"
            + df["gain"].map("{:+,.2f}".format)
            + " "
            + df["gain_pct"].map("{:+.2%}".format)
            + "<br>"
        )
        stocks_qty_text = df["open_qty"].astype(str) + " shares"
        option_qty_text = df["open_qty"].astype(str) + " contracts"

    if not stocks_df.empty:
        stocks_text = (
            common_text
            + stocks_qty_text
            + ", "
            + df["days_held"].map("{:,.0f} days".format)
            + "<br>"
            + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
        )
    else:
        stocks_text = ""

    if not option_df.empty:
        option_text = (
            common_text
            + option_qty_text
            + ", "
            + df["option_dte"].map("{:,.0f} DTE".format)
            + "<br>"
            + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
        )
    else:
        option_text = ""

    df["display_text"] = np.where(
        df["holding_category"].isin(["Call Option", "Put Option"]),
        option_text,
        stocks_text,
    )

    fig = px.treemap(
        data_frame=df,
        path=[px.Constant("Holdings"), df.index],
        values="weight",
        color="gain_pct",
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        custom_data=["display_text"],
        hover_data=(
            ["name", "timestamp"]
            if hide_balances
            else ["name", "market_value", "timestamp"]
        ),
    )

    fig.update_traces(
        textinfo="label+text",
        texttemplate="<b>%{label}</b><br>%{customdata[0]}",
    )

    fig.update_coloraxes(showscale=False)

    fig.update_layout(
        height=height,
        margin=dict(t=0, b=0, l=0, r=0),
    )

    return fig
