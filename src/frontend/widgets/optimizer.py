from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests
import streamlit as st

from frontend.services.streamlit_data import get_api_client

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
        "delta_color": "inverse",
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
# Main render function
# ---------------------------------------------------------------------------


def render_optimizer(
    portfolio_symbols: list[str],
    holdings_data: pd.DataFrame | None,
    portfolio_metrics: pd.DataFrame | None,
    account_id: str | None = None,
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
        selected_metric: str = st.selectbox(
            "Select optimization metric",
            options=list(METRIC_CONFIG.keys()),
            format_func=lambda k: METRIC_CONFIG[k]["label"],
            index=0,
            key="optimizer_metric_select",
        )

        n_p: int = st.slider(
            "Select number of iterations",
            min_value=1000,
            max_value=7500,
            step=500,
            value=5000,
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

        metric_cfg = METRIC_CONFIG[selected_metric]
        st.markdown(
            f"📌 Objective: {metric_cfg['objective']} "
            f"**{selected_metric}** for n= **{n_p}**"
        )

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
                optimal = _find_optimal_portfolio(
                    result.get("portfolios", []), selected_metric
                )
                st.session_state["optimizer_result"] = result
                st.session_state["optimizer_config"] = result.get("config", {})
                st.session_state["optimizer_metric"] = selected_metric
                st.session_state["optimizer_account_id"] = account_id
                st.session_state["optimizer_optimal_weights"] = (
                    optimal.get("weights", {}) if optimal else {}
                )
                st.session_state["_optimizer_optimal_portfolio"] = optimal
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
    run_metric: str | None = st.session_state.get("optimizer_metric")
    optimal: dict | None = st.session_state.get("_optimizer_optimal_portfolio")
    result_account_id = st.session_state.get("optimizer_account_id")

    if result is None or run_metric is None or optimal is None:
        return

    if result_account_id != account_id:
        st.info(
            "Switch back to the account this optimization was run for, or run the optimizer again."
        )
        return

    st.markdown("---")
    st.markdown("#### :material/analytics: Optimization Results")

    # D1 — KPI summary cards
    kpi_keys = _resolve_kpi_keys(run_metric)

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
    st.caption("*Actual weights based on current holdings market value.")

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
    st.caption(
        f"Run at: {run_at} · seed: {seed_display} · "
        f"n={optimizer_config.get('n_p', '?')} · "
        f"symbols: {', '.join(optimizer_config.get('symbols', []))}"
    )
