import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from frontend.shared.accounts import FIXED_INCOME
from frontend.shared.settings import HEIGHT_TREEMAP, MASKED_VALUE
from frontend.shared.time import humanize_timestamp

COLOR_CHANGE = "change_percent"
COLOR_REL_VOLUME = "relative_volume"
REL_VOLUME_COLOR_MAX = 3.0
# Change colours saturate at a fixed move, so one outlier cannot wash out the
# map and a shade means the same move every day.
CHANGE_COLOR_MAX = 0.04
TOTAL_RETURN_COLOR_MAX = 0.25
CHANGE_COLOR_NEUTRAL = "#ECEFF1"
# Red and green differ in lightness so they stay apart under red-green colour
# blindness; tiles also print the signed change, so colour is never the only cue
CHANGE_COLOR_SCALE = ["#D32F2F", CHANGE_COLOR_NEUTRAL, "#15803D"]


def format_cap(fraction: float) -> str:
    """0.04 -> "4%", 0.025 -> "2.5%": a colour cap as written, not rounded."""
    return f"{round(fraction * 100, 2):g}%"


def _diverging_color(column: str, cap: float) -> dict:
    """Red below zero, neutral at zero, green above; full colour at ±cap."""
    return {
        "color": column,
        "color_continuous_scale": CHANGE_COLOR_SCALE,
        "range_color": (-cap, cap),
    }


def compact_number(value: float) -> str:
    """1234 -> "1.2K", 2_627_000 -> "2.6M"; below 1,000 stays whole."""
    if pd.isna(value):
        return "N/A"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        # Compare the rounded value so 999,950 reads 1.0M, not 1000.0K
        if round(abs(value) / threshold, 1) >= 1:
            return f"{value / threshold:.1f}{suffix}"
    return f"{value:,.0f}"


def _size_treemap(
    elements: int, per_row: int = 12, row_px: int = HEIGHT_TREEMAP, base_px: int = 0
) -> int:
    """Dynamically adjust height based on number of elements."""
    rows = (elements + per_row - 1) // per_row
    rows = max(1, rows)
    return base_px + rows * row_px


def _treemap_height(df: pd.DataFrame, row_px: int, group_cols: list[str] | None) -> int:
    """Grouped treemaps add a 24px header per parent and clamp to 3–6 rows so
    tiles shrink instead of the page growing."""
    if not group_cols:
        return _size_treemap(df.shape[0], row_px=row_px)
    n_parents = df.groupby(group_cols, sort=False).ngroups
    height = _size_treemap(df.index.nunique(), row_px=row_px) + 24 * n_parents
    return min(max(height, 3 * row_px), 6 * row_px)


def leaf_labels(df: pd.DataFrame) -> "pd.Series | pd.Index":
    """Tile label per row: OSI for options, else quote symbol.

    Holdings frames may be indexed by a compound key ("account|symbol") in the
    total-portfolio view, so grouped treemaps label leaves from the columns.
    Frames without a symbol column (market pages) keep the index, which is the
    symbol there.
    """
    if "symbol" not in df.columns:
        return df.index
    if "option_osi" in df.columns:
        return df["option_osi"].fillna(df["symbol"])
    return df["symbol"]


# Tile rows line up across the Intraday and Total Return views so a toggle
# swaps content in place: value, change, activity/position, weight, time.
# Lines stay short (abbreviated) because the longest one sets the text size.


def _weight_row(df: pd.DataFrame) -> pd.Series:
    return "<br>" + df["weight"].map("Wt. {:.2%}".format)


def _quote_text(
    df: pd.DataFrame, rel_volume: pd.Series, show_weight: bool = False
) -> pd.Series:
    return (
        df["close"].map("{:,.2f}".format)
        + " "
        + df["currency"]
        + "<br>"
        + df["change"].map("{:+,.2f}".format)
        + " "
        + df["change_percent"].map("{:+.2%}".format)
        + "<br>"
        + df["volume"].map(lambda v: f"Vol. {compact_number(v)}")
        + rel_volume.map(lambda x: "" if pd.isna(x) else f" · {x:.1f}×")
        + (_weight_row(df) if show_weight else "")
        + "<br>"
        + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
    )


def _maturity_text(days: float) -> str:
    if pd.isna(days):
        return ""
    return "matured" if days <= 0 else f"{days:,.0f} d left"


def _maturity_date_row(df: pd.DataFrame) -> pd.Series:
    """Takes the row where a security shows its last trade time."""
    if "fi_maturity_date" not in df.columns:
        return pd.Series("", index=df.index)
    dates = pd.to_datetime(df["fi_maturity_date"], errors="coerce")
    return dates.map(lambda d: "" if pd.isna(d) else f"<br>Mat. {d:%Y-%m-%d}")


def _fixed_income_rows(df: pd.DataFrame, show_weight: bool = True) -> pd.Series:
    """Rows shared by both views: terms, weight, maturity date."""
    return (
        df["fi_rate"].map(lambda r: "" if pd.isna(r) else f"{r:.2%} · ")
        + df["fi_days_to_maturity"].map(_maturity_text)
        + (_weight_row(df) if show_weight else "")
        + _maturity_date_row(df)
    )


def _fixed_income_quote_text(
    df: pd.DataFrame, hide_balances: bool, show_weight: bool
) -> pd.Series:
    value = (
        pd.Series(MASKED_VALUE, index=df.index)
        if hide_balances
        else df["market_value"].map("{:,.2f} CAD".format)
    )
    return value + "<br>No intraday chg<br>" + _fixed_income_rows(df, show_weight)


def render_treemap_intraday(
    df: pd.DataFrame,
    top_label: str = "",
    size_by: str | None = None,
    has_weight: bool = False,
    row_px: int = HEIGHT_TREEMAP,
    hide_balances: bool = False,
    group_cols: list[str] | None = None,
    color_by: str = COLOR_CHANGE,
) -> go.Figure:
    """Intraday treemap; `group_cols` nests symbols under those columns
    (e.g. region -> group). A symbol appearing in several groups renders once
    per parent. Height is capped when grouped — tiles shrink, not the page.

    `color_by` is the change % (diverging red/green) or the relative volume
    (one hue, saturating at REL_VOLUME_COLOR_MAX)."""
    df = df.copy()
    height = _treemap_height(df, row_px, group_cols)
    rel_volume = (
        df["relative_volume"].astype(float)
        if "relative_volume" in df.columns
        else pd.Series(np.nan, index=df.index)
    )

    # Holdings frames only: fixed income has no quote, so it gets a neutral
    # tile sized like any other, keeping the layout of the Total Return view
    is_fixed_income = (
        (df["holding_category"] == FIXED_INCOME).to_numpy()
        if "holding_category" in df.columns
        else np.zeros(len(df), dtype=bool)
    )
    has_fixed_income = bool(is_fixed_income.any())
    show_weight = has_weight and "weight" in df.columns

    if has_fixed_income:
        text = pd.Series("", index=df.index, dtype=object)
        if not is_fixed_income.all():
            text.iloc[np.flatnonzero(~is_fixed_income)] = _quote_text(
                df[~is_fixed_income], rel_volume[~is_fixed_income], show_weight
            ).to_numpy()
        text.iloc[np.flatnonzero(is_fixed_income)] = _fixed_income_quote_text(
            df[is_fixed_income], hide_balances, show_weight
        ).to_numpy()
        df["display_text"] = text
        df.loc[is_fixed_income, "change_percent"] = 0.0
    else:
        df["display_text"] = _quote_text(df, rel_volume, show_weight)

    path: list = [px.Constant(top_label)]
    if has_fixed_income:
        leaves = pd.Series(
            np.asarray(leaf_labels(df) if group_cols else df.index), index=df.index
        )
        df["_leaf"] = _name_fixed_income(
            leaves, df["name"], pd.Series(is_fixed_income, index=df.index)
        )
        path.extend([*(group_cols or []), "_leaf"])
    elif group_cols:
        # An explicit leaf column: passing df.index alongside other path columns
        # is ambiguous to plotly when a column shares the index's name ("symbol").
        df["_leaf"] = leaf_labels(df)
        path.extend([*group_cols, "_leaf"])
    else:
        path.append(df.index)

    base_config = {
        "data_frame": df,
        "path": path,
        "custom_data": ["display_text"],
        "hover_data": ["name", "timestamp"],
    }

    if color_by == COLOR_REL_VOLUME:
        # No traded volume (indices, FX) sits at the quiet end of the scale
        df["_color"] = rel_volume.fillna(0.0).clip(upper=REL_VOLUME_COLOR_MAX)
        base_config["color"] = "_color"
        base_config["color_continuous_scale"] = "Blues"
        base_config["range_color"] = (0, REL_VOLUME_COLOR_MAX)
    else:
        base_config.update(_diverging_color("change_percent", CHANGE_COLOR_MAX))

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


def _name_fixed_income(
    labels: pd.Series, names: pd.Series, is_fixed_income: pd.Series
) -> pd.Series:
    """A fixed-income key is an internal id, so those tiles show the holding
    name; a name shared by several holdings keeps the key so tiles stay apart."""
    shared = names.where(is_fixed_income).duplicated(keep=False)
    return labels.mask(is_fixed_income & ~shared, names)


def render_treemap_positions(
    df: pd.DataFrame,
    row_px: int = HEIGHT_TREEMAP,
    hide_balances: bool = False,
    group_cols: list[str] | None = None,
) -> go.Figure:
    df = df.copy()
    height = _treemap_height(df, row_px, group_cols)

    is_option = df["holding_category"].isin(["Call Option", "Put Option"])
    is_fixed_income = df["holding_category"] == FIXED_INCOME
    option_df = df[is_option]
    stocks_df = df[~is_option & ~is_fixed_income]

    if hide_balances:
        common_text = (
            MASKED_VALUE + "<br>" + df["gain_pct"].map("{:+.2%}".format) + "<br>"
        )
        stocks_qty_text = ""
        option_qty_text = ""
        sep = ""
    else:
        common_text = (
            df["market_value"].map("{:,.2f} CAD".format)
            + "<br>"
            + df["gain"].map("{:+,.2f}".format)
            + " "
            + df["gain_pct"].map("{:+.2%}".format)
            + "<br>"
        )
        stocks_qty_text = df["open_qty"].astype(str) + " sh"
        option_qty_text = df["open_qty"].astype(str) + " ct"
        sep = " · "
    weight_row = _weight_row(df)

    if not stocks_df.empty:
        stocks_text = (
            common_text
            + stocks_qty_text
            + sep
            + df["days_held"].map("{:,.0f} d".format)
            + weight_row
            + "<br>"
            + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
        )
    else:
        stocks_text = ""

    if not option_df.empty:
        option_text = (
            common_text
            + option_qty_text
            + sep
            + df["option_dte"].map("{:,.0f} DTE".format)
            + weight_row
            + "<br>"
            + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
        )
    else:
        option_text = ""

    if is_fixed_income.any():
        fixed_income_text = common_text + _fixed_income_rows(df)
    else:
        fixed_income_text = ""

    df["display_text"] = np.select(
        [is_option, is_fixed_income],
        [option_text, fixed_income_text],
        default=stocks_text,
    )

    leaves = pd.Series(leaf_labels(df) if group_cols else df.index, index=df.index)
    df["_leaf"] = _name_fixed_income(leaves, df["name"], is_fixed_income)
    path: list = [px.Constant("Holdings"), *(group_cols or []), "_leaf"]

    fig = px.treemap(
        data_frame=df,
        path=path,
        values="weight",
        **_diverging_color("gain_pct", TOTAL_RETURN_COLOR_MAX),
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
