import pandas as pd
import streamlit as st

from frontend.presentation.settings import RETURN_HORIZONS
from frontend.presentation.styles import (
    PERFORMANCE_TABLE_CONFIG,
    performance_table_styler,
)
from frontend.presentation.widgets.growth_chart import render_growth_chart
from frontend.presentation.widgets.risk_chart import render_risk_chart
from frontend.shared.config_loader import SymbolGroup


def _render_footer(metrics: pd.DataFrame, bars: pd.DataFrame) -> None:
    """Footer for performance views."""
    last_bar = bars.index.max()
    if isinstance(last_bar, pd.Timestamp) and not pd.isna(last_bar):
        last_bar_str = last_bar.strftime("%Y-%m-%d")
    else:
        last_bar_str = "N/A"

    n_holdings = len(metrics)

    with st.container(horizontal=True, border=False):
        st.caption(
            f"{n_holdings} securities shown · metrics based on trailing 1Y returns data"
        )
        st.badge(
            f"EOD data up to {last_bar_str}",
            icon="📅",
            color="blue",
        )


def render_performance_view(
    risk_free_rate: float,
    key_prefix: str,
    benchmark_metrics: pd.DataFrame | None = None,
    benchmark_close_norm_eod: pd.DataFrame | None = None,
    metrics: pd.DataFrame | None = None,
    close_norm_eod: pd.DataFrame | None = None,
    portfolio_metrics: pd.DataFrame | None = None,
    portfolio_close_norm_eod: pd.DataFrame | None = None,
    use_group_filter: bool = False,
    groups: list[SymbolGroup] = [],
) -> None:
    """EOD performance view: growth, risk, tables.

    Args:
        metrics: Metrics dataframe for securities
        close_norm_eod: Normalized close prices for securities
        benchmark_metrics: Benchmark metrics
        benchmark_close_norm_eod: Benchmark normalized close prices
        risk_free_rate: Risk-free rate
        key_prefix: Prefix for Streamlit widget keys (e.g., "market" or "holdings")
        portfolio_metrics: Optional portfolio metrics (for holdings view)
        portfolio_close_norm_eod: Optional portfolio normalized close prices
        use_group_filter: If True, use group-based filtering; if False, use symbol-based
        groups: List of symbol groups to filter by
    """
    st.markdown("#### :material/trending_up: Performance")
    if metrics is None or metrics.empty:
        st.info("No metrics found")
        return

    c = st.columns(2)

    # Growth chart
    with c[0]:
        st.markdown("##### :material/stacked_line_chart: Growth of $10,000")

        # Filtering logic
        if use_group_filter:
            groups_labels = [group.label for group in groups]
            sel_groups = st.multiselect(
                "Select one or more groups",
                groups_labels,
                default=[groups_labels[0]],
                key=f"{key_prefix}-groups-selector",
            )
            if sel_groups:
                sel_symbols = sorted(
                    {
                        symbol
                        for group in groups
                        if group.label in sel_groups
                        for symbol in group.symbols
                    }
                )
            else:
                sel_symbols = sorted(
                    {symbol for group in groups for symbol in group.symbols}
                )
        else:
            labels = sorted(metrics.index.unique())
            selection = st.multiselect(
                "Filter by symbols",
                labels,
                key=f"{key_prefix}-symbols-selector",
            )
            sel_symbols = (
                metrics.loc[metrics.index.isin(selection)].index.tolist()
                if selection
                else []
            )

        sub_close_norm = (
            close_norm_eod.loc[:, sel_symbols] if sel_symbols else close_norm_eod
        )
        sub_metrics = metrics.loc[sel_symbols] if sel_symbols else metrics

        with st.container(border=True):
            growth_chart_args = [sub_close_norm, benchmark_close_norm_eod]
            if portfolio_close_norm_eod is not None:
                growth_chart_args.append(portfolio_close_norm_eod)
            fig = render_growth_chart(*growth_chart_args)
            st.plotly_chart(fig, key=f"chart-{key_prefix}-growth")

    # Risk/Return chart
    sub_metrics = metrics.loc[sel_symbols] if sel_symbols else metrics

    with c[1]:
        st.markdown("##### :material/scatter_plot: Risk/Return")

        sel_horizon_label = st.radio(
            "Select return range",
            RETURN_HORIZONS.keys(),
            horizontal=True,
            key=f"{key_prefix}-horizon-selector",
        )

        sel_horizon_metric = RETURN_HORIZONS[sel_horizon_label]["metric"]
        sel_horizon_days = RETURN_HORIZONS[sel_horizon_label]["days"]
        sel_horizon_trading_days = RETURN_HORIZONS[sel_horizon_label]["trading_days"]

        with st.container(border=True):
            chart = render_risk_chart(
                sub_metrics,
                risk_free_rate=risk_free_rate,
                horizon_metric=sel_horizon_metric,
                horizon_days=sel_horizon_days,
                horizon_trading_days=sel_horizon_trading_days,
                horizon_label=sel_horizon_label,
                benchmark=benchmark_metrics,
                portfolio=portfolio_metrics,
            )
            st.altair_chart(chart, key=f"chart-{key_prefix}-risk-return")


def render_statistics_table(
    key_prefix: str,
    benchmark_metrics: pd.DataFrame | None = None,
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

    # _render_footer(securities_metrics, sub_close_norm)
