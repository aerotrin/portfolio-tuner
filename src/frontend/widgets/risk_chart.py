import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from frontend.shared.settings import HEIGHT_RISK_RETURN_CHART, TRADING_DAYS_PER_YEAR


def render_risk_chart(
    securities: pd.DataFrame,
    risk_free_rate: float,  # annual % (e.g. 5.0)
    horizon_metric: str,  # PERIOD return column (e.g. "return_1m")
    horizon_label: str,
    horizon_days: int,  # calendar days, not used in math below
    horizon_trading_days: int,  # trading days, used for scaling (n)
    benchmark: pd.DataFrame | None = None,
    portfolio: pd.DataFrame | None = None,
    show_signal: bool = False,
) -> alt.LayerChart:
    # ----------------------------
    # Theme colors
    # ----------------------------
    theme = st.context.theme.type
    base_color = "white" if theme == "dark" else "black"
    benchmark_color = "magenta"

    n = horizon_trading_days  # use horizon_days for calendar days

    # ----------------------------
    # Scale RF (annual -> period)
    # ----------------------------
    rf_ann = risk_free_rate / 100.0
    rf_period = (1.0 + rf_ann) ** (n / TRADING_DAYS_PER_YEAR) - 1.0

    # ----------------------------
    # Build plotting dataframe in PERIOD units
    # ----------------------------
    securities_plot = securities.copy()

    # X: period volatility derived from annualized vol
    securities_plot["volatility_period"] = securities_plot["volatility"] * np.sqrt(
        n / TRADING_DAYS_PER_YEAR
    )

    # Period Sharpe (for sizing)
    volp = securities_plot["volatility_period"].replace(0, np.nan)
    securities_plot["sharpe_period"] = (
        securities_plot[horizon_metric] - rf_period
    ) / volp

    # Do the same transforms for portfolio/benchmark if provided
    benchmark_plot = None
    if benchmark is not None:
        benchmark_plot = benchmark.copy()
        benchmark_plot["volatility_period"] = benchmark_plot["volatility"] * np.sqrt(
            n / TRADING_DAYS_PER_YEAR
        )
        volp_b = benchmark_plot["volatility_period"].replace(0, np.nan)
        benchmark_plot["sharpe_period"] = (
            benchmark_plot[horizon_metric] - rf_period
        ) / volp_b

    portfolio_plot = None
    if portfolio is not None:
        portfolio_plot = portfolio.copy()
        portfolio_plot["volatility_period"] = portfolio_plot["volatility"] * np.sqrt(
            n / TRADING_DAYS_PER_YEAR
        )
        volp_p = portfolio_plot["volatility_period"].replace(0, np.nan)
        portfolio_plot["sharpe_period"] = (
            portfolio_plot[horizon_metric] - rf_period
        ) / volp_p

    # ----------------------------
    # Main scatter: period vol vs period return
    # ----------------------------
    point_selector = alt.selection_point(
        name="symbols",
        fields=["symbol"],
    )  # TODO: Feature is coming in v1.55. See https://github.com/streamlit/streamlit/issues/8643

    base = alt.Chart(securities_plot)

    securities_circles = (
        base.mark_circle()
        .encode(
            x=alt.X(
                "volatility_period:Q",
                title=f"Volatility ({horizon_label})",
                axis=alt.Axis(format=".0%"),
            ),
            y=alt.Y(
                f"{horizon_metric}:Q",
                title=f"{horizon_label} Return",
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color("symbol:N", title="Symbol", legend=None),
            size=alt.Size(
                "weight:Q" if portfolio_plot is not None else "sharpe_period:Q",
                title="Sharpe",
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("symbol:N"),
                alt.Tooltip("name:N"),
                alt.Tooltip(
                    f"{horizon_metric}:Q", title=f"{horizon_label} return", format=".0%"
                ),
                alt.Tooltip(
                    "volatility_period:Q", title=f"Vol ({horizon_label})", format=".0%"
                ),
                alt.Tooltip("volatility:Q", title="Vol (annualized)", format=".0%"),
                alt.Tooltip(
                    "sharpe_period:Q", title=f"Sharpe ({horizon_label})", format=".2f"
                ),
                *(
                    [alt.Tooltip("weight:Q", title="Weight", format=".1%")]
                    if portfolio_plot is not None
                    else []
                ),
            ],
            fillOpacity=alt.condition(point_selector, alt.value(1), alt.value(0.3)),
        )
        .add_params(point_selector)
    )

    label_base = (
        base.transform_calculate(label="datum.symbol + ' ' + datum.signal")
        if show_signal
        else base
    )
    securities_labels = label_base.mark_text(
        dx=10, dy=0, align="left", fontSize=10
    ).encode(
        x="volatility_period:Q",
        y=f"{horizon_metric}:Q",
        text="label:N" if show_signal else "symbol:N",
        color="symbol:N",
    )

    # ----------------------------
    # Risk-free line in PERIOD units
    # ----------------------------
    risk_free_line = (
        alt.Chart(pd.DataFrame({"rf": [rf_period]}))
        .mark_rule(strokeDash=[2, 2], strokeWidth=1.5, opacity=0.25, color=base_color)
        .encode(
            y="rf:Q",
            tooltip=alt.value(
                f"Risk-free over {horizon_label}: {rf_period:.2%} (from {rf_ann:.2%} annual)"
            ),
        )
    )

    layers: list[alt.Chart] = [securities_circles, securities_labels, risk_free_line]

    # ----------------------------
    # Portfolio point
    # ----------------------------
    if portfolio_plot is not None:
        portf_chart = alt.Chart(portfolio_plot)

        portf_circle = portf_chart.mark_point(
            shape="diamond", color=base_color, filled=True
        ).encode(
            x="volatility_period:Q",
            y=f"{horizon_metric}:Q",
            size=alt.value(250),
            tooltip=[
                alt.Tooltip("symbol:N"),
                alt.Tooltip("name:N"),
                alt.Tooltip(
                    f"{horizon_metric}:Q", title=f"{horizon_label} return", format=".0%"
                ),
                alt.Tooltip(
                    "volatility_period:Q", title=f"Vol ({horizon_label})", format=".0%"
                ),
                alt.Tooltip("volatility:Q", title="Vol (annualized)", format=".0%"),
                alt.Tooltip(
                    "sharpe_period:Q", title=f"Sharpe ({horizon_label})", format=".2f"
                ),
            ],
        )

        portf_label = portf_chart.mark_text(
            dx=10,
            dy=0,
            align="left",
            color=base_color,
            fontSize=10,
            fontWeight="bold",
        ).encode(
            text="symbol:N",
            x="volatility_period:Q",
            y=f"{horizon_metric}:Q",
        )

        layers += [portf_circle, portf_label]

    # ----------------------------
    # Benchmark point + guides (period units)
    # ----------------------------
    if benchmark_plot is not None:
        bench_chart = alt.Chart(benchmark_plot)

        bench_circle = bench_chart.mark_point(
            shape="circle", color=benchmark_color
        ).encode(
            x="volatility_period:Q",
            y=f"{horizon_metric}:Q",
            size=alt.value(250)
            if portfolio_plot is not None
            else alt.Size("sharpe_period:Q", title="Sharpe", legend=None),
            tooltip=[
                alt.Tooltip("symbol:N"),
                alt.Tooltip("name:N"),
                alt.Tooltip(
                    f"{horizon_metric}:Q", title=f"{horizon_label} return", format=".0%"
                ),
                alt.Tooltip(
                    "volatility_period:Q", title=f"Vol ({horizon_label})", format=".0%"
                ),
                alt.Tooltip("volatility:Q", title="Vol (annualized)", format=".0%"),
                alt.Tooltip(
                    "sharpe_period:Q", title=f"Sharpe ({horizon_label})", format=".2f"
                ),
            ],
        )

        bench_label = bench_chart.mark_text(
            dx=10, dy=0, align="left", color=benchmark_color, fontSize=10
        ).encode(
            text="symbol:N",
            x="volatility_period:Q",
            y=f"{horizon_metric}:Q",
        )

        bench_vol_p = float(benchmark_plot["volatility_period"].iloc[0])
        bench_ret_p = float(benchmark_plot[horizon_metric].iloc[0])

        vline = (
            alt.Chart(pd.DataFrame({"x": [bench_vol_p]}))
            .mark_rule(color=benchmark_color, strokeDash=[2, 2])
            .encode(x="x:Q")
        )

        hline = (
            alt.Chart(pd.DataFrame({"y": [bench_ret_p]}))
            .mark_rule(color=benchmark_color, strokeDash=[2, 2])
            .encode(y="y:Q")
        )

        layers += [bench_circle, bench_label, vline, hline]

    return alt.layer(*layers).properties(height=HEIGHT_RISK_RETURN_CHART).interactive()
