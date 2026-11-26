from typing import Any, NamedTuple, Sequence

import pandas as pd
import plotly.graph_objects as go

from frontend.shared.settings import (
    CHART_CATEGORICAL_DARK,
    CHART_CATEGORICAL_LIGHT,
    CHART_OTHER_COLOR,
    GREEN,
    HEIGHT_PRICE_CHART_GAP,
    HEIGHT_PRICE_CHART_PANELS,
    RED,
)

PANEL_PRICE = "price"
PANEL_VOLUME = "volume"
PANEL_RSI = "rsi"
PANEL_MACD = "macd"
PANEL_ORDER = (PANEL_PRICE, PANEL_VOLUME, PANEL_RSI, PANEL_MACD)
PANEL_LABELS = {
    PANEL_VOLUME: "Volume",
    PANEL_RSI: "RSI 14",
    PANEL_MACD: "MACD (12, 26, 9)",
}

CHART_CANDLES = "candles"
CHART_LINE = "line"

SERIES_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "bb_middle",
    "bb_upper",
    "bb_lower",
    "rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
)
MARGIN_TOP = 36
MARGIN_BOTTOM = 28
RSI_BAND = (30, 70)


class Panel(NamedTuple):
    name: str
    axis: str  # trace reference: "y", "y2", ...
    layout_key: str  # layout property: "yaxis", "yaxis2", ...
    domain: tuple[float, float]


def chart_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Date-indexed frame from the API's columnar series; nulls become NaN."""
    series = payload.get("series") or {}
    frame = pd.DataFrame(
        {col: series.get(col, []) for col in SERIES_COLUMNS}, dtype=float
    )
    for ma in series.get("moving_averages", []):
        frame[f"ma_{ma['period']}"] = pd.Series(ma["values"], dtype=float)
    frame.index = pd.DatetimeIndex(pd.to_datetime(series.get("dates", [])), name="date")
    return frame


def moving_average_columns(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """(column, legend label) per moving average, e.g. ("ma_20", "SMA 20")."""
    series = payload.get("series") or {}
    return [
        (f"ma_{ma['period']}", f"{str(ma['kind']).upper()} {ma['period']}")
        for ma in series.get("moving_averages", [])
    ]


def slice_to_range(frame: pd.DataFrame, sessions: int) -> pd.DataFrame:
    return frame.tail(sessions) if sessions > 0 else frame.iloc[0:0]


def compute_rangebreaks(dates: pd.DatetimeIndex) -> list[dict[str, Any]]:
    """Hide non-trading days so candles sit side by side.

    Symbols that trade on weekends (crypto) get no breaks at all.
    """
    if len(dates) < 2 or (dates.dayofweek >= 5).any():
        return []
    breaks: list[dict[str, Any]] = [dict(bounds=["sat", "mon"])]
    holidays = pd.bdate_range(dates.min(), dates.max()).difference(dates)
    if len(holidays):
        breaks.append(dict(values=[d.strftime("%Y-%m-%d") for d in holidays]))
    return breaks


def panel_layout(panels: Sequence[str]) -> list[Panel]:
    """Stacked y-axis domains, top to bottom, for the price panel plus extras."""
    names = [PANEL_PRICE] + [p for p in PANEL_ORDER[1:] if p in panels]
    heights = [HEIGHT_PRICE_CHART_PANELS[n] for n in names]
    total = sum(heights) + HEIGHT_PRICE_CHART_GAP * (len(names) - 1)

    out = []
    top = float(total)
    for i, (name, height) in enumerate(zip(names, heights)):
        suffix = "" if i == 0 else str(i + 1)
        out.append(
            Panel(
                name=name,
                axis=f"y{suffix}",
                layout_key=f"yaxis{suffix}",
                domain=((top - height) / total, top / total),
            )
        )
        top -= height + HEIGHT_PRICE_CHART_GAP
    return out


def figure_height(panels: Sequence[str]) -> int:
    names = [PANEL_PRICE] + [p for p in PANEL_ORDER[1:] if p in panels]
    return (
        sum(HEIGHT_PRICE_CHART_PANELS[n] for n in names)
        + HEIGHT_PRICE_CHART_GAP * (len(names) - 1)
        + MARGIN_TOP
        + MARGIN_BOTTOM
    )


def _direction_colors(up: pd.Series) -> list[str]:
    return [GREEN if flag else RED for flag in up]


def _price_tag(
    axis: str, value: float, color: str, background: str | None
) -> dict[str, Any]:
    """Right-edge label; without a background colour it is a filled badge."""
    return dict(
        xref="paper",
        yref=axis,
        x=1,
        y=value,
        xanchor="left",
        showarrow=False,
        text=f"{value:,.2f}",
        font=dict(size=11, color=color if background else "white"),
        bgcolor=background or color,
    )


def build_price_chart_figure(
    df: pd.DataFrame,
    *,
    moving_averages: Sequence[tuple[str, str]] = (),
    chart_type: str = CHART_CANDLES,
    show_bollinger: bool = False,
    panels: Sequence[str] = (),
    show_price_tags: bool = False,
    theme: str = "light",
) -> go.Figure:
    """Stacked daily price chart over the rows of `df` (already range-sliced).

    Every trace shares one x-axis and each panel has its own y-axis domain,
    which is what lets the unified hover span all panels.
    """
    dark = theme == "dark"
    palette = CHART_CATEGORICAL_DARK if dark else CHART_CATEGORICAL_LIGHT
    base_color = "white" if dark else "black"
    # Masks the axis tick underneath a moving-average tag
    background = "#0e1117" if dark else "white"
    layout = panel_layout(panels)
    axes = {panel.name: panel.axis for panel in layout}
    price_axis = axes[PANEL_PRICE]
    x = df.index

    fig = go.Figure()
    annotations: list[dict[str, Any]] = []
    shapes: list[dict[str, Any]] = []

    if show_bollinger and df["bb_upper"].notna().any():
        band = dict(color=CHART_OTHER_COLOR, width=1)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["bb_upper"],
                name="Bollinger upper",
                mode="lines",
                line=band,
                yaxis=price_axis,
                legendgroup="bollinger",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["bb_lower"],
                name="Bollinger (20, 2)",
                mode="lines",
                line=band,
                fill="tonexty",
                fillcolor="rgba(128,128,128,0.12)",
                yaxis=price_axis,
                legendgroup="bollinger",
            )
        )

    if chart_type == CHART_CANDLES:
        fig.add_trace(
            go.Candlestick(
                x=x,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="OHLC",
                yaxis=price_axis,
                increasing=dict(line_color=GREEN, fillcolor=GREEN),
                decreasing=dict(line_color=RED, fillcolor=RED),
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["close"],
                name="Close",
                mode="lines",
                line=dict(color=base_color, width=1.5),
                yaxis=price_axis,
            )
        )

    closes = df["close"].dropna()
    for i, (column, label) in enumerate(moving_averages):
        if column not in df or df[column].notna().sum() == 0:
            continue
        color = palette[i % len(palette)]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df[column],
                name=label,
                mode="lines",
                line=dict(color=color, width=1.2),
                yaxis=price_axis,
            )
        )
        last = df[column].dropna()
        if show_price_tags and not last.empty:
            annotations.append(
                _price_tag(price_axis, float(last.iloc[-1]), color, background)
            )

    if show_price_tags and not closes.empty:
        last_close = float(closes.iloc[-1])
        rising = len(closes) < 2 or last_close >= float(closes.iloc[-2])
        annotations.append(
            _price_tag(price_axis, last_close, GREEN if rising else RED, None)
        )
        shapes.append(
            dict(
                type="line",
                xref="paper",
                yref=price_axis,
                x0=0,
                x1=1,
                y0=last_close,
                y1=last_close,
                line=dict(color=GREEN if rising else RED, width=1, dash="dot"),
            )
        )

    if PANEL_VOLUME in axes:
        fig.add_trace(
            go.Bar(
                x=x,
                y=df["volume"],
                name="Volume",
                marker=dict(color=_direction_colors(df["close"] >= df["open"])),
                opacity=0.6,
                yaxis=axes[PANEL_VOLUME],
                showlegend=False,
            )
        )

    if PANEL_RSI in axes:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["rsi"],
                name="RSI 14",
                mode="lines",
                line=dict(color=palette[6], width=1.2),
                yaxis=axes[PANEL_RSI],
                showlegend=False,
            )
        )
        shapes.append(
            dict(
                type="rect",
                xref="paper",
                yref=axes[PANEL_RSI],
                x0=0,
                x1=1,
                y0=RSI_BAND[0],
                y1=RSI_BAND[1],
                fillcolor="rgba(128,128,128,0.12)",
                line=dict(width=0),
                layer="below",
            )
        )

    if PANEL_MACD in axes:
        fig.add_trace(
            go.Bar(
                x=x,
                y=df["macd_histogram"],
                name="Histogram",
                marker=dict(color=_direction_colors(df["macd_histogram"] >= 0)),
                opacity=0.6,
                yaxis=axes[PANEL_MACD],
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["macd"],
                name="MACD",
                mode="lines",
                line=dict(color=palette[0], width=1.2),
                yaxis=axes[PANEL_MACD],
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["macd_signal"],
                name="Signal",
                mode="lines",
                line=dict(color=palette[1], width=1.2),
                yaxis=axes[PANEL_MACD],
                showlegend=False,
            )
        )

    fig.update_traces(xaxis="x")

    axis_layout: dict[str, Any] = {}
    for panel in layout:
        axis: dict[str, Any] = dict(
            domain=list(panel.domain), side="right", showgrid=True, fixedrange=True
        )
        if panel.name == PANEL_PRICE:
            axis["hoverformat"] = ",.2f"
        elif panel.name == PANEL_VOLUME:
            axis.update(hoverformat=".3s", tickformat=".2s", nticks=3)
        elif panel.name == PANEL_RSI:
            axis.update(range=[0, 100], tickvals=[30, 50, 70], hoverformat=".1f")
        elif panel.name == PANEL_MACD:
            axis.update(hoverformat=".2f", nticks=4)
        axis_layout[panel.layout_key] = axis
        if panel.name in PANEL_LABELS:
            annotations.append(
                dict(
                    xref="paper",
                    yref="paper",
                    x=0,
                    y=panel.domain[1],
                    xanchor="left",
                    yanchor="bottom",
                    showarrow=False,
                    text=PANEL_LABELS[panel.name],
                    font=dict(size=11, color=CHART_OTHER_COLOR),
                )
            )

    fig.update_layout(
        height=figure_height(panels),
        margin=dict(t=MARGIN_TOP, b=MARGIN_BOTTOM, l=0, r=60),
        hovermode="x unified",
        hoversubplots="axis",
        bargap=0.2,
        legend=dict(orientation="h", x=0, xanchor="left", y=1, yanchor="bottom"),
        xaxis=dict(
            type="date",
            anchor=layout[-1].axis,
            rangeslider=dict(visible=False),
            rangebreaks=compute_rangebreaks(x),
            showgrid=True,
        ),
        annotations=annotations,
        shapes=shapes,
        **axis_layout,
    )
    return fig
