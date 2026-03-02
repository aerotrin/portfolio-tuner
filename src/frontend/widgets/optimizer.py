from __future__ import annotations
import logging
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st

from frontend.services.streamlit_data import get_api_client
from frontend.shared.settings import HEIGHT_EFFICIENT_FRONTIER_CHART

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric configuration
# ---------------------------------------------------------------------------

METRIC_CONFIG: dict[str, dict[str, Any]] = {
    "sharpe": {
        "label": "Sharpe Ratio",
        "objective": "Maximize",
        "format_value": lambda v: f"{v:.2f}",
        "format_delta": lambda v: f"{v:+.2f}",
        "delta_color": "normal",
        "best_fn": max,
    },
    "volatility": {
        "label": "Volatility",
        "objective": "Minimize",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "inverse",
        "best_fn": min,
    },
    "max_drawdown": {
        "label": "Max Drawdown",
        "objective": "Minimize",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "normal",
        # max_drawdown is stored as a negative float (e.g. -0.12 for -12%).
        # "Minimize drawdown" = least severe = value closest to 0 = the maximum negative float.
        "best_fn": max,
    },
    "return1Y": {
        "label": "Return 1Y",
        "objective": "Maximize",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "normal",
        "best_fn": max,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_kpi_keys(selected_metric: str) -> list[str]:
    """Return exactly 3 deduplicated metric keys for KPI card display.

    Always starts with [selected_metric, "return1Y", "volatility"], deduplicates
    while preserving order, then pads to 3 with "sharpe" if needed.
    """
    candidates = [selected_metric, "return1Y", "volatility"]
    seen: set[str] = set()
    keys: list[str] = []
    for k in candidates:
        if k not in seen:
            seen.add(k)
            keys.append(k)
    if len(keys) < 3 and "sharpe" not in seen:
        keys.append("sharpe")
    return keys[:3]


def _find_optimal_portfolio(
    portfolios: list[dict],
    metric: str,
) -> dict | None:
    """Return the portfolio dict that best satisfies the metric.

    Direction is determined by METRIC_CONFIG[metric]["best_fn"] (max or min).
    Returns None if portfolios is empty or the metric key is absent.
    """
    if not portfolios:
        return None
    cfg = METRIC_CONFIG.get(metric)
    if cfg is None:
        logger.warning("Unknown metric %r, falling back to sharpe", metric)
        cfg = METRIC_CONFIG["sharpe"]

    best_fn = cfg["best_fn"]
    valid = [p for p in portfolios if metric in p and p[metric] is not None]
    if not valid:
        return None

    return best_fn(valid, key=lambda p: p[metric])


# ---------------------------------------------------------------------------
# Efficient frontier chart
# ---------------------------------------------------------------------------


def _build_frontier_chart(
    portfolios: list[dict],
    optimal: dict,
    portfolio_metrics: pd.DataFrame | None,
    benchmark_data: pd.DataFrame | None,
    risk_free_rate: float,  # annual %, e.g. 5.0
    footer_text: str = "",
) -> alt.LayerChart:
    """Build an Altair layered scatter chart of the simulated efficient frontier."""
    theme = st.context.theme.type
    base_color = "white" if theme == "dark" else "black"
    benchmark_color = "magenta"
    rf_annual = risk_free_rate / 100.0

    # --- Layer 1: scatter cloud of all simulated portfolios -----------------
    df = pd.DataFrame(
        [
            {
                "volatility": p["volatility"],
                "return1Y": p["return1Y"],
                "sharpe": p["sharpe"],
            }
            for p in portfolios
            if "volatility" in p and "return1Y" in p and "sharpe" in p
        ]
    )

    scatter = (
        alt.Chart(df)
        .mark_circle(size=30, opacity=0.5)
        .encode(
            x=alt.X(
                "volatility:Q",
                title="Volatility (annualized)",
                axis=alt.Axis(format=".0%"),
            ),
            y=alt.Y(
                "return1Y:Q",
                title="1Y Return",
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color(
                "sharpe:Q",
                title="Sharpe",
                scale=alt.Scale(scheme="viridis"),
                legend=alt.Legend(),
            ),
            tooltip=[
                alt.Tooltip("volatility:Q", format=".1%", title="Volatility"),
                alt.Tooltip("return1Y:Q", format=".1%", title="1Y Return"),
                alt.Tooltip("sharpe:Q", format=".2f", title="Sharpe"),
            ],
        )
    )

    # --- Layer 2: risk-free horizontal rule ---------------------------------
    rf_line = (
        alt.Chart(pd.DataFrame({"rf": [rf_annual]}))
        .mark_rule(strokeDash=[2, 2], strokeWidth=1.5, opacity=0.4, color=base_color)
        .encode(
            y="rf:Q",
            tooltip=alt.value(f"Risk-free: {rf_annual:.2%} annual"),
        )
    )

    layers: list[Any] = [scatter, rf_line]

    # --- Layer 3: Capital Allocation Line (CAL) ------------------------------
    # CAL always runs from (0, rf) through the max-Sharpe tangency portfolio.
    valid_portfolios = [
        p for p in portfolios if "sharpe" in p and p["sharpe"] is not None
    ]
    if valid_portfolios and not df.empty:
        tangency = max(valid_portfolios, key=lambda p: p["sharpe"])
        t_vol = float(tangency["volatility"])
        t_ret = float(tangency["return1Y"])
        if t_vol > 0:
            slope = (t_ret - rf_annual) / t_vol
            x_max = float(df["volatility"].max()) * 1.3
            cal_df = pd.DataFrame(
                {"x": [0.0, x_max], "y": [rf_annual, rf_annual + slope * x_max]}
            )
            cal_line = (
                alt.Chart(cal_df)
                .mark_line(strokeDash=[5, 3], strokeWidth=1.5, color="orange")
                .encode(
                    x="x:Q",
                    y="y:Q",
                    tooltip=alt.value("Capital Allocation Line"),
                )
            )
            layers.append(cal_line)

    # --- Layer 4: Holdings point (current portfolio) ------------------------
    if (
        portfolio_metrics is not None
        and "PORTF" in portfolio_metrics.index
        and "volatility" in portfolio_metrics.columns
        and "return1Y" in portfolio_metrics.columns
    ):
        portf_row = portfolio_metrics.loc["PORTF"]
        holdings_df = pd.DataFrame(
            [
                {
                    "volatility": float(portf_row["volatility"]),
                    "return1Y": float(portf_row["return1Y"]),
                    "label": "Holdings",
                }
            ]
        )
        holdings_pt = (
            alt.Chart(holdings_df)
            .mark_point(shape="square", size=150, color=base_color, filled=True)
            .encode(
                x="volatility:Q",
                y="return1Y:Q",
                tooltip=[
                    alt.Tooltip("label:N"),
                    alt.Tooltip("volatility:Q", format=".1%", title="Volatility"),
                    alt.Tooltip("return1Y:Q", format=".1%", title="1Y Return"),
                ],
            )
        )
        holdings_lbl = (
            alt.Chart(holdings_df)
            .mark_text(
                dx=10,
                dy=0,
                align="left",
                fontSize=10,
                fontWeight="bold",
                color=base_color,
            )
            .encode(x="volatility:Q", y="return1Y:Q", text="label:N")
        )
        layers += [holdings_pt, holdings_lbl]

    # --- Layer 5: Optimal portfolio point -----------------------------------
    opt_df = pd.DataFrame(
        [
            {
                "volatility": float(optimal["volatility"]),
                "return1Y": float(optimal["return1Y"]),
                "sharpe": float(optimal.get("sharpe", 0)),
                "label": "Optimal",
            }
        ]
    )
    optimal_pt = (
        alt.Chart(opt_df)
        .mark_point(shape="diamond", size=150, color="cyan", filled=True)
        .encode(
            x="volatility:Q",
            y="return1Y:Q",
            tooltip=[
                alt.Tooltip("label:N"),
                alt.Tooltip("volatility:Q", format=".1%", title="Volatility"),
                alt.Tooltip("return1Y:Q", format=".1%", title="1Y Return"),
                alt.Tooltip("sharpe:Q", format=".2f", title="Sharpe"),
            ],
        )
    )
    optimal_lbl = (
        alt.Chart(opt_df)
        .mark_text(
            dx=10, dy=0, align="left", fontSize=10, fontWeight="bold", color="cyan"
        )
        .encode(x="volatility:Q", y="return1Y:Q", text="label:N")
    )
    layers += [optimal_pt, optimal_lbl]

    # --- Layer 6: Benchmark point + crosshairs ------------------------------
    if (
        benchmark_data is not None
        and not benchmark_data.empty
        and "volatility" in benchmark_data.columns
        and "return1Y" in benchmark_data.columns
    ):
        row = benchmark_data.iloc[0]
        bench_vol = float(row["volatility"])
        bench_ret = float(row["return1Y"])
        bench_sym = str(row.get("symbol", "Benchmark"))

        bench_df = pd.DataFrame(
            [{"volatility": bench_vol, "return1Y": bench_ret, "symbol": bench_sym}]
        )
        bench_pt = (
            alt.Chart(bench_df)
            .mark_circle(color=benchmark_color, size=150, filled=False)
            .encode(
                x="volatility:Q",
                y="return1Y:Q",
                tooltip=[
                    alt.Tooltip("symbol:N"),
                    alt.Tooltip("volatility:Q", format=".1%", title="Volatility"),
                    alt.Tooltip("return1Y:Q", format=".1%", title="1Y Return"),
                ],
            )
        )
        bench_lbl = (
            alt.Chart(bench_df)
            .mark_text(dx=10, dy=0, align="left", fontSize=10, color=benchmark_color)
            .encode(x="volatility:Q", y="return1Y:Q", text="symbol:N")
        )
        vline = (
            alt.Chart(pd.DataFrame({"x": [bench_vol]}))
            .mark_rule(color=benchmark_color, strokeDash=[2, 2], opacity=0.5)
            .encode(x="x:Q")
        )
        hline = (
            alt.Chart(pd.DataFrame({"y": [bench_ret]}))
            .mark_rule(color=benchmark_color, strokeDash=[2, 2], opacity=0.5)
            .encode(y="y:Q")
        )
        layers += [bench_pt, bench_lbl, vline, hline]

    props: dict[str, Any] = {"height": HEIGHT_EFFICIENT_FRONTIER_CHART}
    if footer_text:
        props["title"] = alt.TitleParams(
            text=footer_text,
            orient="bottom",
            anchor="start",
            fontSize=12,
            color="gray",
        )
    return alt.layer(*layers).properties(**props).interactive()


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_optimizer(
    portfolio_symbols: list[str],
    holdings_data: pd.DataFrame | None,
    portfolio_metrics: pd.DataFrame | None,
    account_id: str | None = None,
    benchmark_data: pd.DataFrame | None = None,
    risk_free_rate: float = 0.0,
) -> None:
    """Render the Portfolio Weight Optimizer tab.

    Args:
        portfolio_symbols: Sorted list of current holding symbols.
        holdings_data: Wide DataFrame indexed by symbol with a 'weight' column
                       (decimal 0-1 representing current allocation per holding).
        portfolio_metrics: Wide DataFrame indexed by 'symbol', containing a
                           'PORTF' row with actual portfolio metrics.
        account_id: The account the optimizer is running for. Results are only
                    shown when the stored account matches the current one.
        benchmark_data: Optional benchmark metrics DataFrame (has 'volatility',
                        'return1Y', 'symbol' columns) for frontier chart overlay.
        risk_free_rate: Annual risk-free rate as a percentage (e.g. 5.0 = 5%).
    """
    st.markdown("#### :material/tune: Portfolio Weight Optimizer")

    # --- Guard: no holdings -------------------------------------------------
    if not portfolio_symbols:
        st.info(
            "No holdings found. Add positions to your portfolio to use the optimizer."
        )
        return

    # --- Form ---------------------------------------------------------------
    st.selectbox(
        "Select data source",
        options=["Holdings"],
        index=0,
        disabled=True,
        key="optimizer_data_source",
    )

    with st.container(border=True):
        n_p: int = st.slider(
            "Select number of iterations",
            min_value=1000,
            max_value=5000,
            step=500,
            value=2500,
            key="optimizer_n_p_slider",
        )

        seed_raw = st.number_input(
            "Seed (optional, 0–100)",
            min_value=0,
            max_value=100,
            value=None,
            step=1,
            placeholder="Leave blank for random",
            key="optimizer_seed_input",
        )
        seed: int | None = int(seed_raw) if seed_raw is not None else None

        run_clicked = st.button(
            "Run Optimizer",
            type="primary",
            key="optimizer_run_button",
            icon=":material/play_arrow:",
        )

    # --- API call -----------------------------------------------------------
    if run_clicked:
        api = get_api_client()
        with st.spinner("Running optimizer..."):
            try:
                result = api.simulate_portfolios(
                    symbols=portfolio_symbols,
                    n_p=n_p,
                    seed=seed,
                )
                st.session_state["optimizer_result"] = result
                st.session_state["optimizer_config"] = result.get("config", {})
                st.session_state["optimizer_account_id"] = account_id
            except requests.HTTPError as e:
                st.session_state["optimizer_result"] = None
                detail = ""
                if e.response is not None:
                    try:
                        detail = e.response.json().get("detail", "")
                    except Exception:
                        pass
                msg = (
                    detail
                    or f"HTTP {e.response.status_code if e.response is not None else '?'}"
                )
                st.error(f"Optimizer failed: {msg}")
                logger.exception("simulate_portfolios HTTP error: %s", msg)
                return
            except Exception:
                st.session_state["optimizer_result"] = None
                st.error("Optimizer failed: unexpected error. Check logs for details.")
                logger.exception("simulate_portfolios unexpected error")
                return

        st.success("Optimization complete!")

    # --- Results ------------------------------------------------------------
    result: dict | None = st.session_state.get("optimizer_result")
    result_account_id = st.session_state.get("optimizer_account_id")

    if result is None:
        return

    if result_account_id != account_id:
        st.info(
            "Switch back to the account this optimization was run for, or run the optimizer again."
        )
        return

    # Metric selector — drives optimal portfolio selection and all downstream sections
    selected_metric: str = st.selectbox(
        "Optimization metric",
        options=list(METRIC_CONFIG.keys()),
        format_func=lambda k: METRIC_CONFIG[k]["label"],
        index=0,
        key="optimizer_metric_select",
    )

    optimal: dict | None = _find_optimal_portfolio(
        result.get("portfolios", []), selected_metric
    )
    if optimal is None:
        st.warning("No valid portfolios found for the selected metric.")
        return

    st.markdown("---")
    st.markdown("#### :material/analytics: Optimization Results")

    # D1 — KPI summary cards
    kpi_keys = _resolve_kpi_keys(selected_metric)

    st.markdown("##### Optimized Portfolio Summary")
    with st.container(border=True, horizontal=True):
        for key in kpi_keys:
            cfg = METRIC_CONFIG[key]
            opt_val = optimal.get(key)
            if opt_val is None:
                st.metric(cfg["label"], "N/A")
                continue

            delta_str: str | None = None
            if (
                portfolio_metrics is not None
                and "PORTF" in portfolio_metrics.index
                and key in portfolio_metrics.columns
            ):
                actual_val = portfolio_metrics.loc["PORTF", key]
                if actual_val is not None and not pd.isna(actual_val):
                    delta_str = cfg["format_delta"](opt_val - float(actual_val))

            st.metric(
                label=cfg["label"],
                value=cfg["format_value"](opt_val),
                delta=delta_str,
                delta_color=cfg["delta_color"],
            )

    col_left, col_right = st.columns([1, 2])

    with col_left:
        # D2 — Asset Allocation Comparison
        st.markdown("##### Asset Allocation Comparison")

        actual_weights: dict[str, float] = {}
        if holdings_data is not None and "weight" in holdings_data.columns:
            for sym in portfolio_symbols:
                if sym in holdings_data.index:
                    actual_weights[sym] = float(holdings_data.loc[sym, "weight"])

        optimal_weights: dict[str, float] = optimal.get("weights", {})

        alloc_rows = [
            {
                "Symbol": sym,
                "Actual": actual_weights.get(sym, 0.0),
                "Optimal": optimal_weights.get(sym, 0.0),
                "Delta": optimal_weights.get(sym, 0.0) - actual_weights.get(sym, 0.0),
            }
            for sym in sorted(portfolio_symbols)
        ]
        alloc_df = pd.DataFrame(alloc_rows)

        st.dataframe(
            alloc_df,
            hide_index=True,
            column_order=["Symbol", "Actual", "Optimal", "Delta"],
            column_config={
                "Symbol": st.column_config.TextColumn("Symbol"),
                "Actual": st.column_config.NumberColumn("Actual", format="percent"),
                "Optimal": st.column_config.NumberColumn("Optimal", format="percent"),
                "Delta": st.column_config.NumberColumn("Delta", format="percent"),
            },
            key="table-optimizer-allocation",
        )
        st.caption(
            "Actual weights reflect current holdings at market value. "
            "Optimal weights assume no cash allocation."
        )

        # D3 — KPI Comparison
        st.markdown("##### KPI Comparison")

        actual_portf = (
            portfolio_metrics.loc["PORTF"]
            if portfolio_metrics is not None and "PORTF" in portfolio_metrics.index
            else None
        )

        actual_row: dict[str, Any] = {"Scenario": "Actual"}
        optimal_row: dict[str, Any] = {"Scenario": "Optimal"}
        delta_row: dict[str, Any] = {"Scenario": "Delta"}

        for key in kpi_keys:
            cfg = METRIC_CONFIG[key]
            col_label = cfg["label"]

            opt_val = optimal.get(key)
            act_val: float | None = None
            if (
                actual_portf is not None
                and key in actual_portf.index
                and not pd.isna(actual_portf[key])
            ):
                act_val = float(actual_portf[key])

            actual_row[col_label] = (
                cfg["format_value"](act_val) if act_val is not None else "N/A"
            )
            optimal_row[col_label] = (
                cfg["format_value"](opt_val) if opt_val is not None else "N/A"
            )
            if act_val is not None and opt_val is not None:
                delta_row[col_label] = cfg["format_delta"](opt_val - act_val)
            else:
                delta_row[col_label] = "N/A"

        kpi_df = pd.DataFrame([actual_row, optimal_row, delta_row])

        st.dataframe(
            kpi_df,
            hide_index=True,
            key="table-optimizer-kpi-comparison",
        )

        # D4 — Config footer
        optimizer_config = st.session_state.get("optimizer_config", {})
        run_at = optimizer_config.get("run_at", "")
        stored_seed = optimizer_config.get("seed")
        seed_display = str(stored_seed) if stored_seed is not None else "random"
    chart_footer = (
        f"Run at: {run_at} · seed: {seed_display} · "
        f"n={optimizer_config.get('n_p', '?')} · "
    )
    st.caption(chart_footer)

    with col_right:
        # D5 — Efficient Frontier chart
        st.markdown("##### Efficient Frontier")
        with st.container(border=True):
            frontier_chart = _build_frontier_chart(
                portfolios=result.get("portfolios", []),
                optimal=optimal,
                portfolio_metrics=portfolio_metrics,
                benchmark_data=benchmark_data,
                risk_free_rate=risk_free_rate,
                footer_text=chart_footer,
            )
            st.altair_chart(frontier_chart, use_container_width=True)
