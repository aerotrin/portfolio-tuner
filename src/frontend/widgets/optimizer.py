from __future__ import annotations
import logging
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st

from frontend.services.streamlit_data import get_api_client
from frontend.shared.settings import (
    HEIGHT_EFFICIENT_FRONTIER_CHART,
    TRADING_DAYS_PER_YEAR,
)

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
    "sharpe1M": {
        "label": "Sharpe (1M)",
        "objective": "Maximize",
        "format_value": lambda v: f"{v:.2f}",
        "format_delta": lambda v: f"{v:+.2f}",
        "delta_color": "normal",
        "best_fn": max,
    },
    "sharpe3M": {
        "label": "Sharpe (3M)",
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

# Display-only metrics for KPI cards and the comparison table — not selectable
# as optimization objectives, so they live outside METRIC_CONFIG (whose keys
# drive the metric selectbox).
DISPLAY_METRIC_CONFIG: dict[str, dict[str, Any]] = {
    "return1M": {
        "label": "Return (1M)",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "normal",
    },
    "return3M": {
        "label": "Return (3M)",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "normal",
    },
    "volatility1M": {
        "label": "Volatility (1M)",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "inverse",
    },
    "volatility3M": {
        "label": "Volatility (3M)",
        "format_value": lambda v: f"{v:.1%}",
        "format_delta": lambda v: f"{v:+.1%}",
        "delta_color": "inverse",
    },
}

ALL_METRIC_CONFIG: dict[str, dict[str, Any]] = {
    **METRIC_CONFIG,
    **DISPLAY_METRIC_CONFIG,
}

# Dirichlet weight sampling over many assets produces near-uniform weights, so
# simulated portfolios cluster together and the frontier loses meaning. The
# response payload also grows with n_p × symbols.
WARN_OPTIMIZER_SYMBOLS = 25
MAX_OPTIMIZER_SYMBOLS = 50

# Trailing windows (trading days) for frontend-derived period Sharpe ratios.
PERIOD_SHARPE_WINDOWS = {"1M": 21, "3M": 63}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_sharpe(
    period_return: float, annual_volatility: float, risk_free_rate: float, days: int
) -> float:
    """Period excess return over annual volatility rescaled to the window.

    Same definition as the risk chart's sharpe_period: the volatility
    denominator is the full-year estimate scaled by sqrt(days/252), not one
    measured within the window.
    """
    rf_period = (1.0 + risk_free_rate) ** (days / TRADING_DAYS_PER_YEAR) - 1.0
    vol_period = annual_volatility * (days / TRADING_DAYS_PER_YEAR) ** 0.5
    return (period_return - rf_period) / vol_period


def _augment_period_metrics(portfolios: list[dict], risk_free_rate: float) -> None:
    """Stamp period Sharpe and period-scaled volatility onto each record in place.

    sharpe{label} follows the risk chart definition (see _period_sharpe);
    volatility{label} is the annual volatility scaled by sqrt(days/252).
    Records with a missing return window or non-positive volatility get None,
    which _find_optimal_portfolio already excludes.
    """
    for label, days in PERIOD_SHARPE_WINDOWS.items():
        scale = (days / TRADING_DAYS_PER_YEAR) ** 0.5
        for p in portfolios:
            ret = p.get(f"return{label}")
            vol = p.get("volatility")
            vol_ok = vol is not None and not pd.isna(vol) and vol > 0
            p[f"volatility{label}"] = vol * scale if vol_ok else None
            if not vol_ok or ret is None or pd.isna(ret):
                p[f"sharpe{label}"] = None
            else:
                p[f"sharpe{label}"] = _period_sharpe(ret, vol, risk_free_rate, days)


def _with_period_metrics(
    df: pd.DataFrame | None, risk_free_rate: float
) -> pd.DataFrame | None:
    """Return a copy of the actual-portfolio metrics with sharpe and volatility
    1M/3M columns."""
    if df is None or "volatility" not in df.columns:
        return df
    df = df.copy()
    vol = df["volatility"].where(df["volatility"] > 0)
    for label, days in PERIOD_SHARPE_WINDOWS.items():
        vol_period = vol * (days / TRADING_DAYS_PER_YEAR) ** 0.5
        df[f"volatility{label}"] = vol_period
        col = f"return{label}"
        if col not in df.columns:
            continue
        rf_period = (1.0 + risk_free_rate) ** (days / TRADING_DAYS_PER_YEAR) - 1.0
        df[f"sharpe{label}"] = (df[col] - rf_period) / vol_period
    return df


def _resolve_kpi_keys(selected_metric: str) -> list[str]:
    """Return exactly 3 deduplicated metric keys for KPI card display.

    Starts with [selected_metric, return, volatility] where return/volatility
    follow the selected metric's horizon (period fields for sharpe1M/3M, 1Y
    otherwise), deduplicates while preserving order, then pads to 3 with
    "sharpe" if needed.
    """
    _, _, return_field, _, vol_field = _metric_horizon(selected_metric)
    candidates = [selected_metric, return_field, vol_field]
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


def _metric_horizon(metric: str) -> tuple[str, int, str, str, str]:
    """Map the selected metric to a display horizon:
    (label, days, return field, sharpe field, volatility field).

    Period-Sharpe metrics render the frontier and KPIs in their own window;
    everything else keeps the annual view.
    """
    for label, days in PERIOD_SHARPE_WINDOWS.items():
        if metric == f"sharpe{label}":
            return (
                label,
                days,
                f"return{label}",
                f"sharpe{label}",
                f"volatility{label}",
            )
    return "1Y", TRADING_DAYS_PER_YEAR, "return1Y", "sharpe", "volatility"


def _build_frontier_chart(
    portfolios: list[dict],
    optimal: dict,
    portfolio_metrics: pd.DataFrame | None,
    benchmark_data: pd.DataFrame | None,
    risk_free_rate: float,  # annual decimal fraction, e.g. 0.038 = 3.8%
    horizon_label: str = "1Y",
    horizon_days: int = TRADING_DAYS_PER_YEAR,
    return_field: str = "return1Y",
    sharpe_field: str = "sharpe",
    footer_text: str = "",
) -> alt.LayerChart:
    """Build an Altair layered scatter chart of the simulated efficient frontier.

    Renders in the horizon's period space (risk_chart convention): volatility
    scaled by sqrt(days/252), returns over the window, RF compounded to the
    period — for the 1Y horizon this is identical to the annual view.
    """
    theme = st.context.theme.type
    base_color = "white" if theme == "dark" else "black"
    benchmark_color = "magenta"

    scale = (horizon_days / TRADING_DAYS_PER_YEAR) ** 0.5
    rf_period = (1.0 + risk_free_rate) ** (horizon_days / TRADING_DAYS_PER_YEAR) - 1.0
    vol_title = f"Volatility ({horizon_label})"
    ret_title = f"Return ({horizon_label})"
    sharpe_title = f"Sharpe ({horizon_label})"

    # --- Layer 1: scatter cloud of all simulated portfolios -----------------
    df = pd.DataFrame(
        [
            {
                "volatility": p["volatility"] * scale,
                "ret": p[return_field],
                "sharpe": p[sharpe_field],
            }
            for p in portfolios
            if p.get("volatility") is not None
            and p.get(return_field) is not None
            and p.get(sharpe_field) is not None
        ]
    )

    scatter = (
        alt.Chart(df)
        .mark_circle(size=30, opacity=0.5)
        .encode(
            x=alt.X(
                "volatility:Q",
                title=vol_title,
                axis=alt.Axis(format=".0%"),
            ),
            y=alt.Y(
                "ret:Q",
                title=ret_title,
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color(
                "sharpe:Q",
                title=sharpe_title,
                scale=alt.Scale(scheme="viridis"),
                legend=alt.Legend(),
            ),
            tooltip=[
                alt.Tooltip("volatility:Q", format=".1%", title=vol_title),
                alt.Tooltip("ret:Q", format=".1%", title=ret_title),
                alt.Tooltip("sharpe:Q", format=".2f", title=sharpe_title),
            ],
        )
    )

    # --- Layer 2: risk-free horizontal rule ---------------------------------
    rf_line = (
        alt.Chart(pd.DataFrame({"rf": [rf_period]}))
        .mark_rule(strokeDash=[2, 2], strokeWidth=1.5, opacity=0.4, color=base_color)
        .encode(
            y=alt.Y("rf:Q", title=None),
            tooltip=alt.value(f"Risk-free: {rf_period:.2%} ({horizon_label})"),
        )
    )

    layers: list[Any] = [scatter, rf_line]

    # --- Layer 3: Capital Allocation Line (CAL) ------------------------------
    # CAL always runs from (0, rf) through the max-Sharpe tangency portfolio
    # for the active horizon.
    valid_portfolios = [p for p in portfolios if p.get(sharpe_field) is not None]
    if valid_portfolios and not df.empty:
        tangency = max(valid_portfolios, key=lambda p: p[sharpe_field])
        t_vol = float(tangency["volatility"]) * scale
        t_ret = float(tangency[return_field])
        if t_vol > 0:
            slope = (t_ret - rf_period) / t_vol
            x_max = float(df["volatility"].max()) * 1.3
            cal_df = pd.DataFrame(
                {"x": [0.0, x_max], "y": [rf_period, rf_period + slope * x_max]}
            )
            cal_line = (
                alt.Chart(cal_df)
                .mark_line(strokeDash=[5, 3], strokeWidth=1.5, color="orange")
                .encode(
                    x=alt.X("x:Q", title=None),
                    y=alt.Y("y:Q", title=None),
                    tooltip=alt.value("Capital Allocation Line"),
                )
            )
            layers.append(cal_line)

    # --- Layer 4: Holdings point (current portfolio) ------------------------
    if (
        portfolio_metrics is not None
        and "PORTF" in portfolio_metrics.index
        and "volatility" in portfolio_metrics.columns
        and return_field in portfolio_metrics.columns
    ):
        portf_row = portfolio_metrics.loc["PORTF"]
        holdings_df = pd.DataFrame(
            [
                {
                    "volatility": float(portf_row["volatility"]) * scale,
                    "ret": float(portf_row[return_field]),
                    "label": "Holdings",
                }
            ]
        )
        holdings_pt = (
            alt.Chart(holdings_df)
            .mark_point(shape="diamond", size=250, color=base_color, filled=True)
            .encode(
                x=alt.X("volatility:Q", title=None),
                y=alt.Y("ret:Q", title=None),
                tooltip=[
                    alt.Tooltip("label:N"),
                    alt.Tooltip("volatility:Q", format=".1%", title=vol_title),
                    alt.Tooltip("ret:Q", format=".1%", title=ret_title),
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
            .encode(
                x=alt.X("volatility:Q", title=None),
                y=alt.Y("ret:Q", title=None),
                text="label:N",
            )
        )
        layers += [holdings_pt, holdings_lbl]

    # --- Layer 5: Optimal portfolio point -----------------------------------
    opt_sharpe = optimal.get(sharpe_field)
    opt_df = pd.DataFrame(
        [
            {
                "volatility": float(optimal["volatility"]) * scale,
                "ret": float(optimal[return_field]),
                "sharpe": float(opt_sharpe) if opt_sharpe is not None else 0.0,
                "label": "Optimal",
            }
        ]
    )
    optimal_pt = (
        alt.Chart(opt_df)
        .mark_point(shape="diamond", size=250, color="cyan", filled=True)
        .encode(
            x=alt.X("volatility:Q", title=None),
            y=alt.Y("ret:Q", title=None),
            tooltip=[
                alt.Tooltip("label:N"),
                alt.Tooltip("volatility:Q", format=".1%", title=vol_title),
                alt.Tooltip("ret:Q", format=".1%", title=ret_title),
                alt.Tooltip("sharpe:Q", format=".2f", title=sharpe_title),
            ],
        )
    )
    optimal_lbl = (
        alt.Chart(opt_df)
        .mark_text(
            dx=10, dy=0, align="left", fontSize=10, fontWeight="bold", color="cyan"
        )
        .encode(
            x=alt.X("volatility:Q", title=None),
            y=alt.Y("ret:Q", title=None),
            text="label:N",
        )
    )
    layers += [optimal_pt, optimal_lbl]

    # --- Layer 6: Benchmark point + crosshairs ------------------------------
    if (
        benchmark_data is not None
        and not benchmark_data.empty
        and "volatility" in benchmark_data.columns
        and return_field in benchmark_data.columns
    ):
        row = benchmark_data.iloc[0]
        bench_vol = float(row["volatility"]) * scale
        bench_ret = float(row[return_field])
        bench_sym = str(row.get("symbol", "Benchmark"))

        bench_df = pd.DataFrame(
            [{"volatility": bench_vol, "ret": bench_ret, "symbol": bench_sym}]
        )
        bench_pt = (
            alt.Chart(bench_df)
            .mark_circle(color=benchmark_color, size=250, filled=False)
            .encode(
                x=alt.X("volatility:Q", title=None),
                y=alt.Y("ret:Q", title=None),
                tooltip=[
                    alt.Tooltip("symbol:N"),
                    alt.Tooltip("volatility:Q", format=".1%", title=vol_title),
                    alt.Tooltip("ret:Q", format=".1%", title=ret_title),
                ],
            )
        )
        bench_lbl = (
            alt.Chart(bench_df)
            .mark_text(dx=10, dy=0, align="left", fontSize=10, color=benchmark_color)
            .encode(
                x=alt.X("volatility:Q", title=None),
                y=alt.Y("ret:Q", title=None),
                text="symbol:N",
            )
        )
        vline = (
            alt.Chart(pd.DataFrame({"x": [bench_vol]}))
            .mark_rule(color=benchmark_color, strokeDash=[2, 2], opacity=0.5)
            .encode(x=alt.X("x:Q", title=None))
        )
        hline = (
            alt.Chart(pd.DataFrame({"y": [bench_ret]}))
            .mark_rule(color=benchmark_color, strokeDash=[2, 2], opacity=0.5)
            .encode(y=alt.Y("y:Q", title=None))
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
    context_id: str,
    context_label: str,
    benchmark_data: pd.DataFrame | None = None,
    risk_free_rate: float = 0.0,
    data_source_label: str = "Holdings",
) -> None:
    """Render the Portfolio Weight Optimizer tab.

    Args:
        portfolio_symbols: Sorted list of candidate symbols for the optimization.
        holdings_data: Wide DataFrame indexed by symbol with a 'weight' column
                       (decimal 0-1 representing current allocation per holding),
                       or None for research (no-holdings) contexts.
        portfolio_metrics: Wide DataFrame indexed by 'symbol', containing a
                           'PORTF' row with actual portfolio metrics, or None.
        context_id: Namespace for stored results and widget state — one result
                    slot per context (e.g. account id, "market-etf",
                    "market-stock"). Results only render in the context they
                    were run for.
        context_label: Human-readable run context stamped on results
                       (e.g. "TFSA-12345" or "Research").
        benchmark_data: Optional benchmark metrics DataFrame (has 'volatility',
                        'return1Y', 'symbol' columns) for frontier chart overlay.
        risk_free_rate: Annual risk-free rate as a decimal fraction (e.g. 0.038 = 3.8%).
        data_source_label: Label shown in the disabled data-source selector.
    """
    st.markdown("#### :material/tune: Portfolio Weight Optimizer")

    result_key = f"optimizer-{context_id}-result"
    has_holdings = holdings_data is not None

    # --- Guards -------------------------------------------------------------
    if not portfolio_symbols:
        st.info(
            "No holdings found. Add positions to your portfolio to use the optimizer."
            if has_holdings
            else "No symbols selected. Adjust the group filter or table selection "
            "on the Performance tab."
        )
        return

    n_symbols = len(portfolio_symbols)
    if n_symbols > MAX_OPTIMIZER_SYMBOLS:
        st.error(
            f"Too many symbols selected ({n_symbols}). The optimizer supports at "
            f"most {MAX_OPTIMIZER_SYMBOLS} — narrow the selection on the "
            "Performance tab via the group filter or table selection."
        )
        return
    if n_symbols > WARN_OPTIMIZER_SYMBOLS:
        st.warning(
            f"Optimizing over {n_symbols} symbols: random weight sampling spreads "
            "thin across many assets, so simulated portfolios cluster together and "
            "results become less meaningful. Consider narrowing the selection."
        )

    # --- Form ---------------------------------------------------------------
    st.selectbox(
        "Select data source",
        options=[data_source_label],
        index=0,
        disabled=True,
        key=f"optimizer-{context_id}-data-source",
    )

    with st.container(border=True):
        n_p: int = st.slider(
            "Select number of iterations",
            min_value=1000,
            max_value=5000,
            step=500,
            value=2500,
            key=f"optimizer-{context_id}-n-p-slider",
        )

        seed_raw = st.number_input(
            "Seed (optional, 0–100)",
            min_value=0,
            max_value=100,
            value=None,
            step=1,
            placeholder="Leave blank for random",
            key=f"optimizer-{context_id}-seed-input",
        )
        seed: int | None = int(seed_raw) if seed_raw is not None else None

        run_clicked = st.button(
            "Run Optimizer",
            type="primary",
            key=f"optimizer-{context_id}-run-button",
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
                st.session_state[result_key] = result
            except requests.HTTPError as e:
                st.session_state[result_key] = None
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
                st.session_state[result_key] = None
                st.error("Optimizer failed: unexpected error. Check logs for details.")
                logger.exception("simulate_portfolios unexpected error")
                return

        st.success("Optimization complete!")

    # --- Results ------------------------------------------------------------
    result: dict | None = st.session_state.get(result_key)

    if result is None:
        return

    _augment_period_metrics(result.get("portfolios", []), risk_free_rate)
    portfolio_metrics = _with_period_metrics(portfolio_metrics, risk_free_rate)

    optimizer_config = result.get("config", {})
    run_symbols: list[str] = optimizer_config.get("symbols", [])
    run_at = optimizer_config.get("run_at", "")
    stored_seed = optimizer_config.get("seed")
    seed_display = str(stored_seed) if stored_seed is not None else "random"

    st.markdown("---")
    st.markdown("#### :material/analytics: Optimization Results")
    st.caption(f"{context_label} · {len(run_symbols)} symbols · run at {run_at}")

    if sorted(run_symbols) != sorted(portfolio_symbols):
        st.info(
            f"Selection has changed since this run ({len(run_symbols)} → "
            f"{n_symbols} symbols) — run the optimizer again to update."
        )

    # Metric selector — drives optimal portfolio selection and all downstream sections
    selected_metric: str = st.selectbox(
        "Select optimization metric",
        options=list(METRIC_CONFIG.keys()),
        format_func=lambda k: METRIC_CONFIG[k]["label"],
        index=0,
        key=f"optimizer-{context_id}-metric-select",
    )

    optimal: dict | None = _find_optimal_portfolio(
        result.get("portfolios", []), selected_metric
    )
    if optimal is None:
        st.warning("No valid portfolios found for the selected metric.")
        return

    # D1 — KPI summary cards
    kpi_keys = _resolve_kpi_keys(selected_metric)

    _metric_cfg = METRIC_CONFIG[selected_metric]
    objective_text = f"Objective: {_metric_cfg['objective']} {_metric_cfg['label']}"
    st.markdown("##### Optimized Portfolio Summary")
    st.markdown(f"*{objective_text}*")

    with st.container(border=True, horizontal=True):
        for key in kpi_keys:
            cfg = ALL_METRIC_CONFIG[key]
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
        st.markdown(
            "##### Asset Allocation Comparison"
            if has_holdings
            else "##### Optimal Asset Allocation"
        )

        show_actual = has_holdings and "weight" in holdings_data.columns
        actual_weights: dict[str, float] = {}
        if show_actual:
            # Sum per quote symbol — holdings may carry several rows per symbol
            # (stock + OSI-keyed options), and option exposure rolls up to the
            # underlying.
            weight_by_symbol = holdings_data.groupby("symbol")["weight"].sum()
            for sym in run_symbols:
                if sym in weight_by_symbol.index:
                    actual_weights[sym] = float(weight_by_symbol[sym])

        optimal_weights: dict[str, float] = optimal.get("weights", {})

        alloc_rows = [
            {
                "Symbol": sym,
                "Actual": actual_weights.get(sym, 0.0),
                "Optimal": optimal_weights.get(sym, 0.0),
                "Delta": optimal_weights.get(sym, 0.0) - actual_weights.get(sym, 0.0),
            }
            for sym in sorted(run_symbols)
        ]
        alloc_df = pd.DataFrame(alloc_rows).sort_values(
            "Optimal", ascending=False, ignore_index=True
        )

        st.dataframe(
            alloc_df,
            hide_index=True,
            column_order=(
                ["Symbol", "Actual", "Optimal", "Delta"]
                if show_actual
                else ["Symbol", "Optimal"]
            ),
            column_config={
                "Symbol": st.column_config.TextColumn("Symbol"),
                "Actual": st.column_config.NumberColumn("Actual", format="percent"),
                "Optimal": st.column_config.NumberColumn("Optimal", format="percent"),
                "Delta": st.column_config.NumberColumn("Delta", format="percent"),
            },
            key=f"table-optimizer-{context_id}-allocation",
        )
        st.caption(
            "Actual weights reflect current holdings at market value. "
            "Optimal weights assume no cash allocation."
            if show_actual
            else "Optimal weights assume no cash allocation."
        )

    # D3 — Config footer
    chart_footer = (
        f"Run at: {run_at} · seed: {seed_display} · "
        f"n={optimizer_config.get('n_p', '?')} · {objective_text} · "
        f"{context_label} · {len(run_symbols)} symbols"
    )

    with col_right:
        # D4 — Efficient Frontier chart
        horizon_label, horizon_days, return_field, sharpe_field, _ = _metric_horizon(
            selected_metric
        )
        st.markdown("##### Efficient Frontier")
        with st.container(border=True):
            frontier_chart = _build_frontier_chart(
                portfolios=result.get("portfolios", []),
                optimal=optimal,
                portfolio_metrics=portfolio_metrics,
                benchmark_data=benchmark_data,
                risk_free_rate=risk_free_rate,
                horizon_label=horizon_label,
                horizon_days=horizon_days,
                return_field=return_field,
                sharpe_field=sharpe_field,
                footer_text=chart_footer,
            )
            st.altair_chart(frontier_chart, width="stretch")
