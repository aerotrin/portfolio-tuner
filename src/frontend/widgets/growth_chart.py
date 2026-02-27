import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_growth_chart(*args: pd.DataFrame) -> go.Figure:
    benchmark_symbol = st.session_state["benchmark"]

    df = pd.concat(args, axis=1).sort_index().ffill()
    df = df.loc[:, ~df.columns.duplicated(keep="first")]  # <- kill duplicate symbols

    # Detect Streamlit theme (dark/light)
    theme = st.context.theme.type
    base_color = "white" if theme == "dark" else "black"
    benchmark_color = "magenta"

    fig = px.line(
        df,
        hover_name="symbol",
    )
    fig.update_traces(line_width=1, mode="lines")
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=0, r=50),
        yaxis_title="Normalized Close",
        xaxis_title="Date",
    )

    # Highlight portfolio
    for trace in fig.data:
        if trace.name == "PORTF":  # type: ignore[attr-defined]
            trace.line.width = 2  # type: ignore[attr-defined]
            trace.line.color = base_color  # type: ignore[attr-defined]
        elif trace.name == benchmark_symbol:  # type: ignore[attr-defined]
            # trace.line.width = 2
            trace.line.color = benchmark_color  # type: ignore[attr-defined]
            trace.line.dash = "dot"  # type: ignore[attr-defined]

    # Add text labels at end of lines
    for trace in fig.data:
        fig.add_annotation(
            x=1.01,
            xref="paper",
            y=trace.y[-1],  # type: ignore[attr-defined]
            text=trace.name,  # type: ignore[attr-defined]
            showarrow=False,
            yref="y",
            xanchor="left",
            font=dict(size=11, color=trace.line.color),  # type: ignore[attr-defined]
        )

    # Add date range selector
    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(step="all", label="MAX"),
                ]
            ),
            rangeslider=dict(visible=False),
            type="date",
        )
    )

    # Add gridlines
    fig.update_yaxes(
        showgrid=True,
    )
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        dtick="M3",
    )

    return fig
