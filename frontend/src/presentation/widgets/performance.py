import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.presentation.settings import MOVER_SHOW_COUNT, RETURN_HORIZONS, HEIGHT_TREEMAP
from src.presentation.styles import (
    PERFORMANCE_TABLE_CONFIG,
    POSITIONS_TABLE_CONFIG,
    QUOTE_TABLE_CONFIG,
    performance_table_styler,
    positions_table_styler,
    quote_table_styler,
)
from src.presentation.widgets.growth_chart import render_growth_chart
from src.presentation.widgets.risk_chart import render_risk_chart
from src.shared.config_loader import SymbolGroup
from src.utils.dataframe import normalize_trends
from src.utils.time import humanize_timestamp


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
) -> go.Figure:
    df = df.copy()

    height = _size_treemap(df.shape[0])

    df["display_text"] = (
        df["close"].map("{:,.2f}".format)
        + " "
        + df["currency"]
        + "<br>"
        + df["change"].map("{:+,.2f}".format)
        + " "
        + df["changePercent"].map("{:.2%}".format)
        + "<br>"
        + df["volume"].map("Vol. {:,.0f}".format)
        + "<br>"
        + df["timestamp"].map(lambda x: humanize_timestamp(x)[0])
    )

    base_config = {
        "data_frame": df,
        "path": [px.Constant(top_label), df.index],
        "color": "changePercent",
        "color_continuous_scale": "RdYlGn",
        "color_continuous_midpoint": 0,
        "custom_data": ["display_text"],
        "hover_data": ["name", "timestamp"],
    }

    if has_weight:
        base_config["values"] = "weight"
        base_config["hover_data"] = [
            "name",
            "timestamp",
            "market_value",
            "gain",
            "gain_pct",
        ]

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


def render_treemap_positions(df: pd.DataFrame) -> go.Figure:
    df = df.copy()

    height = _size_treemap(df.shape[0])

    df["display_text"] = (
        df["market_value"].map("{:,.2f} CAD".format)
        + "<br>"
        + df["gain"].map("{:+,.2f}".format)
        + " "
        + df["gain_pct"].map("{:.2%}".format)
        + "<br>"
        + df["open_qty"].astype(str)
        + " shares"
        + "<br>"
        + df["days_held"].map("{:,.0f} days open".format)
    )

    fig = px.treemap(
        data_frame=df,
        path=[px.Constant("Holdings"), df.index],
        values="market_value",
        color="gain_pct",
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        custom_data=["display_text"],
        hover_data=["weight", "timestamp"],
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


def render_market_intraday(
    market_intraday: pd.DataFrame, groups: list[SymbolGroup], type: str, key_prefix: str
) -> None:
    """Intraday view for market-wide symbols, grouped by thematic group."""

    t_str = type if type.isupper() else type.title()

    st.markdown(f"#### :material/show_chart: {t_str} Intraday")

    label = st.segmented_control(
        f"Select {t_str} group",
        [v.label for v in groups],
        default=groups[0].label,
        label_visibility="collapsed",
        key=f"{key_prefix}-intraday-viewer-view-selector",
    )
    group = next((g for g in groups if g.label == label), None)

    if group is None:
        st.info("Please select a group")
        return

    sub = market_intraday[market_intraday.index.isin(group.symbols)]
    if sub.empty:
        st.info("No symbols found for the selected group")
        return

    fig = render_treemap_intraday(
        sub, top_label=group.label, size_by=None, has_weight=False
    )
    st.plotly_chart(fig, key=f"{key_prefix}-chart-intraday-viewer-{group.label}")
    # st.caption("Size is based on trading volume")

    with st.expander(
        f"{group.label} {t_str} Quote Table",
        icon=":material/table:",
    ):
        st.dataframe(
            quote_table_styler(sub),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
            key=f"{key_prefix}-table-intraday-viewer-{group.label}-quote",
        )


def render_market_movers(
    market_intraday: pd.DataFrame,
    type: str,
) -> None:
    """Intraday view for market movers."""
    # 1. Get the symbols for the market

    df = market_intraday.copy()
    t_str = type if type.isupper() else type.title()

    c = st.columns([7, 1])
    with c[0]:
        st.markdown(f"#### :material/notifications_active: {t_str} Market Movers")

    with c[1]:
        market = st.segmented_control(
            "Select market",
            ["US", "Canada"],
            default="US",
            label_visibility="collapsed",
            key=f"market-movers-selector-{type}",
        )
    currency = "CAD" if market == "Canada" else "USD"
    sub_df = df[df["currency"] == currency]
    if sub_df.empty:
        st.info("No symbols found for the selected market")
        return

    volume_df = sub_df.sort_values(by="volume", ascending=False).head(MOVER_SHOW_COUNT)
    up_df = (
        sub_df[sub_df["changePercent"] > 0]
        .sort_values(by="changePercent", ascending=False)
        .head(MOVER_SHOW_COUNT)
    )
    down_df = (
        sub_df[sub_df["changePercent"] < 0]
        .sort_values(by="changePercent", ascending=True)
        .head(MOVER_SHOW_COUNT)
    )

    st.markdown(f"##### :material/swap_horiz: Most Active {t_str}s")
    fig = render_treemap_intraday(volume_df, top_label="Most Active", has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"Most Active {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(volume_df),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
        )

    st.markdown(f"##### :material/arrow_upward: Top {t_str} Gainers ")
    fig = render_treemap_intraday(up_df, top_label="Top Gainers", has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"Top Gainers {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(up_df),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
        )

    st.markdown(f"##### :material/arrow_downward: Top {t_str} Losers ")
    fig = render_treemap_intraday(down_df, top_label="Top Losers", has_weight=False)
    st.plotly_chart(fig)
    with st.expander(f"Top Losers {t_str} Quote Table", icon=":material/table:"):
        st.dataframe(
            quote_table_styler(down_df),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
        )


def render_holdings_intraday(holdings_intraday: pd.DataFrame | None) -> None:
    """Intraday view for current account holdings."""
    st.markdown("#### :material/show_chart: Intraday")

    if holdings_intraday is None:
        st.info("No holdings found")
        return

    fig = render_treemap_intraday(
        holdings_intraday, top_label="Holdings", has_weight=True
    )
    st.plotly_chart(fig, key="chart-holdings-securities")
    st.caption("Size is based on weight in portfolio")
    with st.expander("Holdings Quote Table", icon=":material/table:", expanded=False):
        st.dataframe(
            quote_table_styler(holdings_intraday),
            hide_index=True,
            column_order=QUOTE_TABLE_CONFIG.keys(),
            column_config=QUOTE_TABLE_CONFIG,
            key="table-holdings-quote",
        )


def render_holdings_allocation(holdings_intraday: pd.DataFrame | None) -> None:
    """Allocation breakdown for current holdings."""
    st.markdown("#### :material/pie_chart: Allocation")

    cash_value = st.session_state["portfolio_summary"]["cash_balance"]
    cash_weight = st.session_state["portfolio_summary"]["cash_pct"]
    cash_row = {
        "symbol": "CASH",
        "name": "Cash",
        "currency": "CAD",
        "market_value": cash_value,
        "book_value": cash_value,
        "security_type": "Cash",
        "holding_category": "Cash",
        "sector": "N/A Cash",
        "industry": "N/A Cash",
        "weight": cash_weight,
    }
    allocation_df = (
        holdings_intraday.copy() if holdings_intraday is not None else pd.DataFrame()
    )
    cash_df = pd.DataFrame([cash_row])
    cash_df.index = ["CASH"]
    allocation_df = pd.concat([allocation_df, cash_df])

    cols = st.columns(2)
    with cols[0]:
        st.markdown("##### By Instrument")
        st.bar_chart(
            allocation_df,
            x="security_type",
            y_label="Held as",
            y="market_value",
            x_label="Market Value CAD",
            color="symbol",
            horizontal=True,
        )

        st.markdown("##### By Currency")
        st.bar_chart(
            allocation_df,
            x="currency",
            y_label="Held in",
            y="market_value",
            x_label="Market Value CAD",
            color="symbol",
            horizontal=True,
        )

    with cols[1]:
        st.markdown("##### By Holding")
        fig = px.pie(
            allocation_df,
            names="symbol",
            values="market_value",
            color="symbol",
            hover_data=["name"],
            height=450,
            hole=0.3,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig)


def render_footer(metrics: pd.DataFrame, bars: pd.DataFrame) -> None:
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


def render_positions(holdings_intraday: pd.DataFrame | None) -> None:
    """Positions breakdown for current holdings (size + table)."""
    st.markdown("#### :material/table_rows: Positions")

    if holdings_intraday is None:
        st.info("No holdings found")
        return

    # Metrics
    with st.container(border=True, horizontal=True):
        st.metric(
            "Current P/L CAD",
            f"${holdings_intraday['gain'].sum():,.2f}",
            f"{holdings_intraday['intraday_gain'].sum():+,.2f}",
        )
        st.metric(
            "Day Best Performer CAD",
            f"{holdings_intraday['symbol'][holdings_intraday['intraday_gain'].idxmax()]}",
            f"{holdings_intraday['intraday_gain'].max():+,.2f}",
        )
        st.metric(
            "Day Worst Performer CAD",
            f"{holdings_intraday['symbol'][holdings_intraday['intraday_gain'].idxmin()]}",
            f"{holdings_intraday['intraday_gain'].min():+,.2f}",
        )
        st.metric(
            "Total FX Exposure",
            f"${holdings_intraday['fx_exposure'].sum():,.2f}",
        )
        st.metric("No. of Holdings", f"{len(holdings_intraday)}")
        st.metric(
            "Average Days Open",
            f"{holdings_intraday['days_held'].mean():.0f}",
        )

    # Treemap
    fig = render_treemap_positions(holdings_intraday)
    st.plotly_chart(fig, key="chart-holdings-open")

    # Health bar
    g = holdings_intraday["gain_pct"].gt(0).sum()
    l = holdings_intraday["gain_pct"].lt(0).sum()
    health_bar = "🟩" * g + "🟥" * l
    st.caption(f"{health_bar}   |   {len(holdings_intraday)} positions (↑ {g}, ↓ {l})")

    # Table
    st.dataframe(
        positions_table_styler(holdings_intraday),
        hide_index=True,
        column_order=POSITIONS_TABLE_CONFIG.keys(),
        column_config=POSITIONS_TABLE_CONFIG,
        key="table-holdings-open",
    )


def _render_performance_view(
    metrics_eod: pd.DataFrame,
    close_norm_eod: pd.DataFrame,
    benchmark_metrics_eod: pd.DataFrame,
    benchmark_close_norm_eod: pd.DataFrame,
    risk_free_rate: float,
    key_prefix: str,
    portfolio_metrics_eod: pd.DataFrame | None = None,
    portfolio_close_norm_eod: pd.DataFrame | None = None,
    use_group_filter: bool = False,
    groups: list[SymbolGroup] = [],
) -> None:
    """EOD performance view: growth, risk, tables.

    Args:
        metrics_eod: Metrics dataframe for securities
        close_norm_eod: Normalized close prices for securities
        benchmark_metrics_eod: Benchmark metrics
        benchmark_close_norm_eod: Benchmark normalized close prices
        risk_free_rate: Risk-free rate
        key_prefix: Prefix for Streamlit widget keys (e.g., "market" or "holdings")
        portfolio_metrics_eod: Optional portfolio metrics (for holdings view)
        portfolio_close_norm_eod: Optional portfolio normalized close prices
        use_group_filter: If True, use group-based filtering; if False, use symbol-based
        groups: List of symbol groups to filter by
    """
    c = st.columns(2)

    # Growth chart
    with c[0]:
        st.markdown("#### :material/trending_up: Growth of $10,000")

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
            labels = sorted(metrics_eod.index.unique())
            selection = st.multiselect(
                "Filter by symbols",
                labels,
                key=f"{key_prefix}-symbols-selector",
            )
            sel_symbols = (
                metrics_eod.loc[metrics_eod.index.isin(selection)].index.tolist()
                if selection
                else []
            )

        sub_close_norm = (
            close_norm_eod.loc[:, sel_symbols] if sel_symbols else close_norm_eod
        )
        sub_metrics = metrics_eod.loc[sel_symbols] if sel_symbols else metrics_eod
        sub_metrics = normalize_trends(sub_metrics)

        with st.container(border=True):
            growth_chart_args = [sub_close_norm, benchmark_close_norm_eod]
            if portfolio_close_norm_eod is not None:
                growth_chart_args.append(portfolio_close_norm_eod)
            fig = render_growth_chart(*growth_chart_args)
            st.plotly_chart(fig, key=f"chart-{key_prefix}-growth")

    # Risk/Return chart
    with c[1]:
        st.markdown("#### :material/scatter_plot: Risk/Return")

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
                benchmark=benchmark_metrics_eod,
                portfolio=portfolio_metrics_eod,
            )
            st.altair_chart(chart, key=f"chart-{key_prefix}-risk-return")

    st.divider()

    # Tables
    st.markdown("#### :material/calculate: Metrics")
    if portfolio_metrics_eod is not None:
        st.markdown("##### Portfolio Statistics")
        with st.container(border=True, horizontal=True):
            pm = portfolio_metrics_eod.iloc[0]
            bm = benchmark_metrics_eod.iloc[0]

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
            performance_table_styler(portfolio_metrics_eod),
            hide_index=True,
            column_order=PERFORMANCE_TABLE_CONFIG.keys(),
            column_config=PERFORMANCE_TABLE_CONFIG,
            key=f"table-{key_prefix}-portfolio-performance",
        )

    st.markdown("##### Benchmark")
    st.dataframe(
        performance_table_styler(benchmark_metrics_eod),
        hide_index=True,
        column_order=PERFORMANCE_TABLE_CONFIG.keys(),
        column_config=PERFORMANCE_TABLE_CONFIG,
        key=f"table-{key_prefix}-benchmark-performance",
    )

    st.markdown("##### Securities")
    st.dataframe(
        performance_table_styler(sub_metrics),
        hide_index=True,
        column_order=PERFORMANCE_TABLE_CONFIG.keys(),
        column_config=PERFORMANCE_TABLE_CONFIG,
        key=f"table-{key_prefix}-security-performance",
    )

    render_footer(sub_metrics, sub_close_norm)

    st.divider()


def _top_corr_pairs(
    corr: pd.DataFrame, n: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # keep only upper triangle (exclude diagonal)
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    pairs = upper.stack().reset_index()
    pairs.columns = ["A", "B", "Correlation"]
    highest = pairs.sort_values("Correlation", ascending=False).head(n)
    lowest = pairs.sort_values("Correlation", ascending=True).head(n)

    return highest, lowest


def render_correlation_matrix(matrix: pd.DataFrame) -> None:
    """Render correlation matrix for current holdings."""
    st.markdown("#### :material/stacked_line_chart: Correlation")

    c = st.columns(2)
    with c[0]:
        st.markdown("##### Correlation Matrix")
        with st.container(border=True):
            fig = px.imshow(
                matrix.values,
                x=matrix.columns,
                y=matrix.index,
                zmin=-1,
                zmax=1,
                color_continuous_scale="RdYlGn_r",
                aspect="auto",
                # text_auto=True,
            )
            st.plotly_chart(fig, width="stretch")

        st.download_button(
            "Download CSV",
            matrix.to_csv().encode(),
            "correlation_matrix.csv",
            "text/csv",
        )

    with c[1]:
        highest, lowest = _top_corr_pairs(matrix)

        if highest.empty or lowest.empty:
            st.warning("No correlation pairs found")
            return

        st.markdown("##### Strongest Correlation Pairs")
        st.dataframe(
            highest,
            hide_index=True,
        )

        st.markdown("##### Weakest Correlation Pairs")
        st.dataframe(
            lowest,
            hide_index=True,
        )

        with st.container(border=True, horizontal=True):
            st.metric(
                "Strongest Pair",
                f"{highest.iloc[0].A} / {highest.iloc[0].B}",
                f"{highest.iloc[0].Correlation:.3f}",
                delta_color="inverse",
                delta_arrow="off",
            )
            st.metric(
                "Weakest Pair",
                f"{lowest.iloc[0].A} / {lowest.iloc[0].B}",
                f"{lowest.iloc[0].Correlation:.3f}",
                delta_color="inverse",
                delta_arrow="off",
            )

    st.divider()


def render_market_performance(
    market_metrics_eod: pd.DataFrame,
    market_close_norm_eod: pd.DataFrame,
    benchmark_metrics_eod: pd.DataFrame,
    benchmark_close_norm_eod: pd.DataFrame,
    risk_free_rate: float,
    groups: list[SymbolGroup],
    key_prefix: str,
) -> None:
    """EOD performance view for market symbols: growth, risk, tables."""
    _render_performance_view(
        metrics_eod=market_metrics_eod,
        close_norm_eod=market_close_norm_eod,
        benchmark_metrics_eod=benchmark_metrics_eod,
        benchmark_close_norm_eod=benchmark_close_norm_eod,
        risk_free_rate=risk_free_rate,
        key_prefix=key_prefix,
        use_group_filter=True,
        groups=groups,
    )


def render_holdings_performance(
    holdings_metrics_eod: pd.DataFrame,
    holdings_close_norm_eod: pd.DataFrame,
    portfolio_metrics_eod: pd.DataFrame,
    portfolio_close_norm_eod: pd.DataFrame,
    benchmark_metrics_eod: pd.DataFrame,
    benchmark_close_norm_eod: pd.DataFrame,
    risk_free_rate: float,
) -> None:
    """EOD performance view for current holdings + portfolio aggregate."""
    _render_performance_view(
        metrics_eod=holdings_metrics_eod,
        close_norm_eod=holdings_close_norm_eod,
        benchmark_metrics_eod=benchmark_metrics_eod,
        benchmark_close_norm_eod=benchmark_close_norm_eod,
        risk_free_rate=risk_free_rate,
        key_prefix="holdings",
        portfolio_metrics_eod=portfolio_metrics_eod,
        portfolio_close_norm_eod=portfolio_close_norm_eod,
        use_group_filter=False,
    )
