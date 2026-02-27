import pandas as pd
import streamlit as st

from frontend.shared.config_loader import SymbolGroup
from frontend.shared.settings import RETURN_HORIZONS
from frontend.widgets.growth_chart import render_growth_chart
from frontend.widgets.risk_chart import render_risk_chart


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
