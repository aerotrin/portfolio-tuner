import pandas as pd
import streamlit as st

from frontend.shared.symbols_loader import SymbolGroup
from frontend.shared.settings import RETURN_HORIZONS
from frontend.shared.styles import PERFORMANCE_TABLE_CONFIG, performance_table_styler
from frontend.widgets.growth_chart import render_growth_chart
from frontend.widgets.risk_chart import render_risk_chart


def render_performance_view(
    risk_free_rate: float,
    key_prefix: str,
    benchmark_metrics: pd.DataFrame,
    benchmark_close_norm_eod: pd.DataFrame | None = None,
    metrics: pd.DataFrame | None = None,
    close_norm_eod: pd.DataFrame | None = None,
    portfolio_metrics: pd.DataFrame | None = None,
    portfolio_close_norm_eod: pd.DataFrame | None = None,
    use_group_filter: bool = False,
    groups: list[SymbolGroup] = [],
) -> None:
    """EOD performance view: growth chart, risk/return chart, and statistics tables.

    Args:
        risk_free_rate: Risk-free rate
        key_prefix: Prefix for Streamlit widget keys (e.g., "market-etf" or "holdings")
        benchmark_metrics: Benchmark metrics
        benchmark_close_norm_eod: Benchmark normalized close prices
        metrics: Metrics dataframe for securities
        close_norm_eod: Normalized close prices for securities
        portfolio_metrics: Optional portfolio metrics (for holdings view)
        portfolio_close_norm_eod: Optional portfolio normalized close prices
        use_group_filter: If True, use group-based filtering; if False, no filter widget
        groups: List of symbol groups to filter by
    """
    st.markdown("#### :material/trending_up: Performance")
    if metrics is None or metrics.empty:
        st.info("No metrics found")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    # Defaults overridden by widgets that render inside the chart columns below.
    sel_horizon_label = next(iter(RETURN_HORIZONS))
    show_signal = True
    groups_labels = [group.label for group in groups]
    if use_group_filter:
        # Read the group multiselect value from session state so that sel_symbols
        # is available for derived state before the widget renders inside c[0].
        _raw_sel: list[str] = st.session_state.get(
            f"{key_prefix}-groups-selector",
            [groups_labels[0]] if groups_labels else [],
        )
        _sel_groups = _raw_sel if _raw_sel else groups_labels
        sel_symbols = sorted(
            {
                symbol
                for group in groups
                if group.label in _sel_groups
                for symbol in group.symbols
            }
        )
    else:
        sel_symbols = []

    # ── Derived state ─────────────────────────────────────────────────────────
    sub_metrics = metrics.loc[sel_symbols] if sel_symbols else metrics

    # Detect group filter change → bump version so the table widget re-creates
    # fresh with empty selection (avoids stale row-index mappings).
    curr_sub_syms = sorted(sub_metrics.index.tolist())
    if st.session_state.get(f"{key_prefix}-sub-symbols") != curr_sub_syms:
        st.session_state[f"{key_prefix}-sub-symbols"] = curr_sub_syms
        st.session_state[f"{key_prefix}-table-version"] = (
            st.session_state.get(f"{key_prefix}-table-version", 0) + 1
        )

    # Versioned table key — local variable shared within this function.
    # Streamlit writes widget state under this key before each rerun, so
    # reading it here gives the current selection before the widget renders.
    table_version = st.session_state.get(f"{key_prefix}-table-version", 0)
    table_key = f"table-{key_prefix}-security-performance-v{table_version}"

    table_state = st.session_state.get(table_key, {})
    selected_rows = table_state.get("selection", {}).get("rows", [])
    selected_in_sub = {
        sub_metrics.index[i] for i in selected_rows if i < len(sub_metrics)
    }
    chart_symbols = (
        sorted(s for s in sub_metrics.index if s in selected_in_sub)
        if selected_in_sub
        else sorted(sub_metrics.index)
    )
    chart_close_norm = close_norm_eod[chart_symbols]
    chart_metrics = sub_metrics.loc[chart_symbols]

    # ── Charts ────────────────────────────────────────────────────────────────
    if use_group_filter:
        st.multiselect(
            ":material/filter_list: Filter by groups",
            groups_labels,
            default=[groups_labels[0]] if groups_labels else [],
            key=f"{key_prefix}-groups-selector",
        )

    h = st.columns(2)
    with h[0]:
        st.markdown("##### :material/stacked_line_chart: Growth of $10,000")

    with h[1]:
        rh = st.columns([9, 1], vertical_alignment="center")
        with rh[0]:
            st.markdown("##### :material/scatter_plot: Risk/Return")
        with rh[1]:
            with st.popover(":material/settings:", type="tertiary"):
                sel_horizon_label = st.radio(
                    "Return range",
                    RETURN_HORIZONS.keys(),
                    horizontal=True,
                    key=f"{key_prefix}-horizon-selector",
                )
                show_signal = st.checkbox(
                    "Signal",
                    value=True,
                    key=f"{key_prefix}-signal-checkbox",
                )

    sel_horizon = RETURN_HORIZONS[sel_horizon_label]

    c = st.columns(2)
    with c[0]:
        with st.container(border=True):
            growth_chart_args = [chart_close_norm, benchmark_close_norm_eod]
            if portfolio_close_norm_eod is not None:
                growth_chart_args.append(portfolio_close_norm_eod)
            fig = render_growth_chart(*growth_chart_args)
            st.plotly_chart(fig, key=f"chart-{key_prefix}-growth")

    with c[1]:
        with st.container(border=True):
            chart = render_risk_chart(
                chart_metrics,
                risk_free_rate=risk_free_rate,
                horizon_metric=sel_horizon["metric"],
                horizon_days=sel_horizon["days"],
                horizon_trading_days=sel_horizon["trading_days"],
                horizon_label=sel_horizon_label,
                benchmark=benchmark_metrics,
                portfolio=portfolio_metrics,
                show_signal=show_signal,
            )
            st.altair_chart(chart, key=f"chart-{key_prefix}-risk-return")

    # ── Statistics tables ─────────────────────────────────────────────────────
    if portfolio_metrics is not None:
        with st.container(border=True, horizontal=True):
            pm = portfolio_metrics.iloc[0]
            bm = benchmark_metrics.iloc[0]

            annual_return = pm["return1Y"]
            benchmark_return = bm["return1Y"]
            annual_volatility = pm["volatility"]
            benchmark_volatility = bm["volatility"]
            max_drawdown = pm["max_drawdown"]
            annual_sharpe = pm["sharpe"]
            benchmark_sharpe = bm["sharpe"]
            annual_sortino = pm["sortino"]
            benchmark_sortino = bm["sortino"]
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

    st.markdown("##### Securities")
    event = st.dataframe(
        performance_table_styler(sub_metrics),
        hide_index=True,
        column_order=PERFORMANCE_TABLE_CONFIG.keys(),
        column_config=PERFORMANCE_TABLE_CONFIG,
        key=table_key,
        on_select="rerun",
        selection_mode="multi-row",
    )
    n_selected = len(event.get("selection", {}).get("rows", []))
    selection_label = f" · {n_selected} selected" if n_selected else ""
    with st.container(horizontal=True, border=False):
        st.caption(
            f"{len(sub_metrics)} securities shown{selection_label} · metrics based on trailing 1Y returns data"
        )
