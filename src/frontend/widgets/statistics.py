import pandas as pd
import streamlit as st

from frontend.shared.styles import PERFORMANCE_TABLE_CONFIG, performance_table_styler


def render_statistics_table(
    key_prefix: str,
    benchmark_metrics: pd.DataFrame,
    securities_metrics: pd.DataFrame | None = None,
    portfolio_metrics: pd.DataFrame | None = None,
) -> None:
    # Tables
    st.markdown("#### :material/calculate: Statistics")

    if securities_metrics is None or securities_metrics.empty:
        st.info("No securities metrics found")
        return

    if portfolio_metrics is not None:
        with st.container(border=True, horizontal=True):
            pm = portfolio_metrics.iloc[0]
            bm = benchmark_metrics.iloc[0]

            # Returns
            annual_return = pm["return1Y"]
            benchmark_return = bm["return1Y"]

            # Risk
            annual_volatility = pm["volatility"]
            benchmark_volatility = bm["volatility"]
            max_drawdown = pm["max_drawdown"]

            # Risk-adjusted
            annual_sharpe = pm["sharpe"]
            benchmark_sharpe = bm["sharpe"]
            annual_sortino = pm["sortino"]
            benchmark_sortino = bm["sortino"]

            # Dates
            max_drawdown_date = pd.to_datetime(pm["max_drawdown_date"]).strftime(
                "%Y-%m-%d"
            )

            st.metric(
                "Return (1Y)",
                f"{annual_return:.1%}",
                f"{annual_return - benchmark_return:+.1%}",
                delta_arrow="off",
            )
            st.metric(
                "Volatility (1Y)",
                f"{annual_volatility:.1%}",
                f"{annual_volatility - benchmark_volatility:+.1%}",
                delta_arrow="off",
                delta_color="inverse",
            )
            st.metric(
                "Sharpe Ratio (1Y)",
                f"{annual_sharpe:.3f}",
                f"{annual_sharpe - benchmark_sharpe:+.3f}",
                delta_arrow="off",
            )
            st.metric(
                "Sortino Ratio (1Y)",
                f"{annual_sortino:.3f}",
                f"{annual_sortino - benchmark_sortino:+.3f}",
                delta_arrow="off",
            )
            st.metric(
                "Max Drawdown",
                f"{max_drawdown:.1%}",
                f"{max_drawdown_date}",
                delta_arrow="off",
                delta_color="blue",
            )

        st.caption(
            rf"Trailing 1Y, annualized. Delta vs. {st.session_state['benchmark']} benchmark."
        )

        st.markdown("##### Portfolio")
        st.dataframe(
            performance_table_styler(portfolio_metrics),
            hide_index=True,
            column_order=PERFORMANCE_TABLE_CONFIG.keys(),
            column_config=PERFORMANCE_TABLE_CONFIG,
            key=f"table-{key_prefix}-portfolio-performance",
        )

    st.markdown("##### Benchmark")
    st.dataframe(
        performance_table_styler(benchmark_metrics),
        hide_index=True,
        column_order=PERFORMANCE_TABLE_CONFIG.keys(),
        column_config=PERFORMANCE_TABLE_CONFIG,
        key=f"table-{key_prefix}-benchmark-performance",
    )

    if securities_metrics is not None:
        st.markdown("##### Securities")
        st.dataframe(
            performance_table_styler(securities_metrics),
            hide_index=True,
            column_order=PERFORMANCE_TABLE_CONFIG.keys(),
            column_config=PERFORMANCE_TABLE_CONFIG,
            key=f"table-{key_prefix}-security-performance",
        )

    with st.container(horizontal=True, border=False):
        st.caption(
            f"{len(securities_metrics)} securities shown · metrics based on trailing 1Y returns data"
        )
