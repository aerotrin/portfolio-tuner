from collections import Counter
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from frontend.shared.settings import (
    ALLOCATION_TOP_HOLDINGS,
    CHART_CATEGORICAL_DARK,
    CHART_CATEGORICAL_LIGHT,
    CHART_OTHER_COLOR,
    DONUT_CASH_COLOR,
    HEIGHT_ALLOCATION_CHART,
    MASKED_VALUE,
    TRADE_SIZING_GUIDE,
)

CASH_LABEL = "Cash"
OTHER_LABEL = "Other"
DIMENSION_LABELS = {
    "asset_type": "Asset type",
    "instrument": "Instrument",
    "sector": "Sector",
    "country": "Country",
    "currency": "Currency",
    "account": "Account",
}
RISK_MEASURES = ["Weight", "Risk share"]
BAR_ROW_HEIGHT = 24
HEIGHT_BREAKDOWN_DONUT = 240


def _palette(dark: bool) -> list[str]:
    return CHART_CATEGORICAL_DARK if dark else CHART_CATEGORICAL_LIGHT


def _color_scale(labels: list[str], dark: bool) -> alt.Scale:
    """Fixed color per label: slots go to labels in alphabetical order so a
    label keeps its color when values change rank; Cash and Other stay grey."""
    palette = _palette(dark)
    named = sorted(x for x in set(labels) if x not in (CASH_LABEL, OTHER_LABEL))
    colors = {label: palette[i % len(palette)] for i, label in enumerate(named)}
    colors[CASH_LABEL] = DONUT_CASH_COLOR
    colors[OTHER_LABEL] = CHART_OTHER_COLOR
    domain = list(dict.fromkeys(labels))
    return alt.Scale(domain=domain, range=[colors[x] for x in domain])


def _value_tooltip(hide_balances: bool) -> list[alt.Tooltip]:
    if hide_balances:
        return []
    return [alt.Tooltip("market_value:Q", title="Value (CAD)", format="$,.0f")]


def _breakdown_frame(
    slices: list[dict[str, Any]],
    labels: dict[str, str] | None = None,
    max_named: int = len(CHART_CATEGORICAL_LIGHT),
) -> pd.DataFrame:
    """Slices largest first; named categories beyond the palette fold into
    Other, and Cash and Other sit last."""
    columns = ["label", "market_value", "weight"]
    df = pd.DataFrame(slices, columns=columns)
    if df.empty:
        return df
    if labels:
        df["label"] = df["label"].map(lambda x: labels.get(x, x))
    df = df.sort_values("market_value", ascending=False)
    cash = df[df["label"] == CASH_LABEL]
    named = df[df["label"] != CASH_LABEL]
    head, tail = named.iloc[:max_named], named.iloc[max_named:]
    parts = [head]
    if not tail.empty:
        other = tail[["market_value", "weight"]].sum()
        parts.append(pd.DataFrame([{"label": OTHER_LABEL, **other.to_dict()}]))
    parts.append(cash)
    return pd.concat(parts, ignore_index=True)[columns]


def _holding_labels(by_symbol: list[dict[str, Any]]) -> dict[str, str]:
    """Display label per symbol. A fixed-income key is an internal id, so that
    holding shows its name unless another fixed-income holding shares it."""
    fixed_income = [r for r in by_symbol if r.get("fixed_income_value", 0) > 0]
    counts = Counter(r["name"] for r in fixed_income)
    return {r["symbol"]: r["name"] for r in fixed_income if counts[r["name"]] == 1}


def _holdings_frame(
    by_symbol: list[dict[str, Any]],
    cash_slice: dict[str, Any] | None,
    top_n: int = ALLOCATION_TOP_HOLDINGS,
) -> pd.DataFrame:
    """Top holdings by weight, then an Other bar for the rest and a Cash bar."""
    labels = _holding_labels(by_symbol)
    columns = [
        "label",
        "name",
        "kind",
        "market_value",
        "weight",
        "shares_value",
        "options_value",
        "fixed_income_value",
    ]
    df = pd.DataFrame(by_symbol)
    if not df.empty and "fixed_income_value" not in df:
        df["fixed_income_value"] = 0.0
    rows: list[dict[str, Any]] = []
    if not df.empty:
        df = df.sort_values("market_value", ascending=False)
        head, tail = df.iloc[:top_n], df.iloc[top_n:]
        rows = [
            {**r, "label": labels.get(r["symbol"], r["symbol"]), "kind": "Holding"}
            for r in head.to_dict("records")
        ]
        if not tail.empty:
            sums = tail[
                [
                    "market_value",
                    "weight",
                    "shares_value",
                    "options_value",
                    "fixed_income_value",
                ]
            ].sum()
            rows.append(
                {
                    "label": OTHER_LABEL,
                    "name": f"{len(tail)} smaller holdings",
                    "kind": OTHER_LABEL,
                    **sums.to_dict(),
                }
            )
    if cash_slice:
        rows.append(
            {
                "label": CASH_LABEL,
                "name": CASH_LABEL,
                "kind": CASH_LABEL,
                "market_value": cash_slice["market_value"],
                "weight": cash_slice["weight"],
                "shares_value": 0.0,
                "options_value": 0.0,
                "fixed_income_value": 0.0,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _risk_frame(
    risk: list[dict[str, Any]],
    top_n: int = ALLOCATION_TOP_HOLDINGS,
    labels: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Long frame (symbol, measure, value) for the largest measured holdings,
    plus the symbols without enough price history to measure."""
    labels = labels or {}
    unmeasured = [r["symbol"] for r in risk if r.get("risk_share") is None]
    measured = [r for r in risk if r.get("risk_share") is not None]
    measured = sorted(measured, key=lambda r: r["weight"], reverse=True)[:top_n]
    rows = []
    for r in measured:
        symbol = labels.get(r["symbol"], r["symbol"])
        rows.append(
            {"symbol": symbol, "measure": RISK_MEASURES[0], "value": r["weight"]}
        )
        rows.append(
            {"symbol": symbol, "measure": RISK_MEASURES[1], "value": r["risk_share"]}
        )
    return pd.DataFrame(rows, columns=["symbol", "measure", "value"]), unmeasured


def _account_mix_frame(
    mix: list[dict[str, Any]], labels: dict[str, str] | None = None
) -> pd.DataFrame:
    columns = ["account", "label", "market_value", "weight"]
    df = pd.DataFrame(mix, columns=columns)
    if not df.empty and labels:
        df["account"] = df["account"].map(lambda x: labels.get(x, x))
    return df


def _build_breakdown_donut(
    df: pd.DataFrame, title: str, dark: bool, hide_balances: bool
) -> alt.Chart:
    df = df.assign(rank=range(len(df)))
    return (
        alt.Chart(df)
        .mark_arc(
            innerRadius=alt.ExprRef(expr="min(width, height) * 0.3"),
            padAngle=0.02,
            cornerRadius=3,
        )
        .encode(
            theta=alt.Theta("weight:Q", stack=True),
            order=alt.Order("rank:Q"),
            color=alt.Color(
                "label:N",
                scale=_color_scale(df["label"].tolist(), dark),
                legend=alt.Legend(title=None, orient="right"),
            ),
            tooltip=[
                alt.Tooltip("label:N", title=title),
                alt.Tooltip("weight:Q", title="Share", format=".1%"),
                *_value_tooltip(hide_balances),
            ],
        )
        .properties(height=HEIGHT_BREAKDOWN_DONUT)
    )


def _build_ranked_bar(df: pd.DataFrame, dark: bool, hide_balances: bool) -> alt.Chart:
    tooltip = [
        alt.Tooltip("label:N", title="Holding"),
        alt.Tooltip("name:N", title="Name"),
        alt.Tooltip("weight:Q", title="Share of portfolio", format=".1%"),
    ]
    if not hide_balances:
        tooltip += [
            *_value_tooltip(hide_balances),
            alt.Tooltip("shares_value:Q", title="In shares", format="$,.0f"),
            alt.Tooltip("options_value:Q", title="In options", format="$,.0f"),
            alt.Tooltip(
                "fixed_income_value:Q", title="In fixed income", format="$,.0f"
            ),
        ]
    base = alt.Chart(df).encode(
        y=alt.Y("label:N", sort=None, title=None),
        x=alt.X(
            "weight:Q",
            title="Share of portfolio",
            axis=alt.Axis(format=".0%"),
            scale=alt.Scale(domainMin=0, nice=True),
        ),
    )
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        color=alt.Color(
            "kind:N",
            scale=alt.Scale(
                domain=["Holding", OTHER_LABEL, CASH_LABEL],
                range=[_palette(dark)[0], CHART_OTHER_COLOR, DONUT_CASH_COLOR],
            ),
            legend=None,
        ),
        tooltip=tooltip,
    )
    text = base.mark_text(
        align="left", dx=4, color="white" if dark else "black"
    ).encode(text=alt.Text("weight:Q", format=".1%"))
    return (bars + text).properties(
        height=max(HEIGHT_ALLOCATION_CHART, BAR_ROW_HEIGHT * len(df))
    )


def _build_risk_bar(df: pd.DataFrame, dark: bool) -> alt.Chart:
    palette = _palette(dark)
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X(
                "symbol:N",
                sort=list(dict.fromkeys(df["symbol"])),
                title=None,
                axis=alt.Axis(labelAngle=-45),
            ),
            xOffset=alt.XOffset("measure:N", sort=RISK_MEASURES),
            y=alt.Y(
                "value:Q",
                title="Share of invested holdings",
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color(
                "measure:N",
                scale=alt.Scale(domain=RISK_MEASURES, range=palette[:2]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("symbol:N", title="Holding"),
                alt.Tooltip("measure:N", title="Measure"),
                alt.Tooltip("value:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=HEIGHT_ALLOCATION_CHART)
    )


def _build_account_mix_bar(
    df: pd.DataFrame, dark: bool, hide_balances: bool
) -> alt.Chart:
    order = df.groupby("label")["market_value"].sum().sort_values(ascending=False)
    labels = [x for x in order.index if x != CASH_LABEL]
    if CASH_LABEL in order.index:
        labels.append(CASH_LABEL)
    df = df.assign(rank=df["label"].map({x: i for i, x in enumerate(labels)}))
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            y=alt.Y("account:N", title=None),
            x=alt.X(
                "weight:Q",
                stack="zero",
                title="Share of account",
                axis=alt.Axis(format=".0%"),
                scale=alt.Scale(domain=[0, 1]),
            ),
            order=alt.Order("rank:Q"),
            color=alt.Color(
                "label:N",
                scale=_color_scale(labels, dark),
                legend=alt.Legend(title=None, orient="right"),
            ),
            tooltip=[
                alt.Tooltip("account:N", title="Account"),
                alt.Tooltip("label:N", title="Asset type"),
                alt.Tooltip("weight:Q", title="Share of account", format=".1%"),
                *_value_tooltip(hide_balances),
            ],
        )
        .properties(height=max(140, 40 * df["account"].nunique() + 70))
    )


def _slice_weight(slices: list[dict[str, Any]], label: str) -> float:
    return next((s["weight"] for s in slices if s["label"] == label), 0.0)


def _render_concentration_kpis(allocation: dict[str, Any]) -> None:
    concentration = allocation.get("concentration", {})
    breakdowns = allocation.get("breakdowns", {})
    by_symbol = allocation.get("by_symbol", [])
    largest = (
        _holding_labels(by_symbol).get(by_symbol[0]["symbol"], by_symbol[0]["symbol"])
        if by_symbol
        else None
    )
    invested_help = "Share of invested holdings, excluding cash."

    with st.container(border=True, horizontal=True):
        st.metric("Holdings", concentration.get("holdings", 0))
        st.metric(
            f"Largest ({largest})" if largest else "Largest",
            f"{concentration.get('top1', 0.0):.1%}",
            help=invested_help,
        )
        st.metric("Top 5", f"{concentration.get('top5', 0.0):.1%}", help=invested_help)
        st.metric(
            "Effective holdings",
            f"{concentration.get('effective_n', 0.0):.1f}",
            help=(
                "How many equal-sized positions would be as concentrated as "
                "this portfolio (1 / sum of squared weights). The further below "
                "the holdings count, the more a few positions dominate."
            ),
        )
        st.metric(
            "Cash",
            f"{_slice_weight(breakdowns.get('instrument', []), CASH_LABEL):.1%}",
        )
        st.metric(
            "USD exposure",
            f"{_slice_weight(breakdowns.get('currency', []), 'USD'):.1%}",
            help="Holdings quoted in USD plus cash in USD accounts.",
        )


def _render_breakdown(
    allocation: dict[str, Any],
    account_labels: dict[str, str] | None,
    dark: bool,
    hide_balances: bool,
    context_id: str,
) -> None:
    breakdowns = allocation.get("breakdowns", {})
    dimensions = [
        d
        for d in DIMENSION_LABELS
        if breakdowns.get(d) and (d != "account" or len(breakdowns[d]) > 1)
    ]
    st.markdown("##### Breakdown")
    dimension = (
        st.segmented_control(
            "Break down by",
            options=dimensions,
            format_func=DIMENSION_LABELS.get,
            default=dimensions[0],
            key=f"allocation-{context_id}-dimension",
            label_visibility="collapsed",
        )
        or dimensions[0]
    )
    title = DIMENSION_LABELS[dimension]
    df = _breakdown_frame(
        breakdowns[dimension], account_labels if dimension == "account" else None
    )
    st.altair_chart(
        _build_breakdown_donut(df, title, dark, hide_balances),
        width="stretch",
        key=f"allocation-{context_id}-breakdown-chart",
    )
    column_config: dict[str, Any] = {
        "label": st.column_config.TextColumn(title),
        "weight": st.column_config.ProgressColumn(
            "Share", format="percent", min_value=0.0, max_value=1.0
        ),
        "market_value": st.column_config.NumberColumn("Value (CAD)", format="dollar"),
    }
    st.dataframe(
        df,
        hide_index=True,
        column_config=column_config,
        column_order=(
            ["label", "weight"]
            if hide_balances
            else ["label", "weight", "market_value"]
        ),
        key=f"allocation-{context_id}-breakdown-table",
    )


def _render_sizing_guide(total_value: float, hide_balances: bool) -> None:
    with st.expander("Position sizing guide", icon=":material/straighten:"):
        st.caption("Dollar size of a new position at each share of the portfolio.")
        guide = pd.DataFrame(
            {
                "Position size": list(TRADE_SIZING_GUIDE),
                "Amount (CAD)": [
                    MASKED_VALUE if hide_balances else f"${pct * total_value:,.2f}"
                    for pct in TRADE_SIZING_GUIDE.values()
                ],
            }
        )
        st.dataframe(guide, hide_index=True, width="content")


def render_portfolio_allocation(
    portfolio_summary: dict[str, Any],
    allocation: dict[str, Any],
    hide_balances: bool,
    context_id: str,
    account_labels: dict[str, str] | None = None,
) -> None:
    """Allocation tab: concentration, breakdowns, holdings and risk shares.

    `account_labels` maps account numbers to display labels (already masked
    when account numbers are hidden).
    """
    st.markdown("#### :material/pie_chart: Allocation")

    breakdowns = (allocation or {}).get("breakdowns", {})
    if not breakdowns.get("instrument"):
        st.info("No holdings or cash to allocate.")
        return

    dark = st.context.theme.type == "dark"
    _render_concentration_kpis(allocation)

    margin = allocation.get("margin", 0.0)
    if margin > 0:
        amount = MASKED_VALUE if hide_balances else f"${margin:,.2f} CAD"
        st.caption(
            f":material/info: Negative cash of {amount} is borrowing, not an "
            "allocation, so shares here are of holdings plus positive cash."
        )

    left, right = st.columns([2, 3])
    with left, st.container(border=True):
        _render_breakdown(allocation, account_labels, dark, hide_balances, context_id)

    with right, st.container(border=True, height="stretch"):
        st.markdown("##### Holdings by weight")
        cash = next(
            (s for s in breakdowns["instrument"] if s["label"] == CASH_LABEL), None
        )
        holdings = _holdings_frame(allocation.get("by_symbol", []), cash)
        st.altair_chart(
            _build_ranked_bar(holdings, dark, hide_balances),
            width="stretch",
            height="stretch",
            key=f"allocation-{context_id}-holdings-chart",
        )
        st.caption(
            "One bar per symbol across accounts. Options are counted under "
            "their underlying, at intrinsic value; fixed income at accrued value."
        )

    risk, unmeasured = _risk_frame(
        allocation.get("risk_contribution", []),
        labels=_holding_labels(allocation.get("by_symbol", [])),
    )
    if not risk.empty:
        with st.container(border=True):
            st.markdown("##### Capital vs risk")
            st.altair_chart(
                _build_risk_bar(risk, dark),
                width="stretch",
                key=f"allocation-{context_id}-risk-chart",
            )
            caption = (
                "Weight is each holding's share of invested value; risk share is "
                "its share of the portfolio's volatility over the past year of "
                "daily returns. A risk share well above the weight marks a "
                "position that drives more of the swings than its size suggests. "
                "Options are treated as their underlying; fixed income holds its "
                "value, so its risk share is zero."
            )
            if unmeasured:
                caption += (
                    " Not measured (too little price history): "
                    + ", ".join(unmeasured)
                    + "."
                )
            st.caption(caption)

    mix = _account_mix_frame(allocation.get("account_mix", []), account_labels)
    if not mix.empty:
        with st.container(border=True):
            st.markdown("##### Asset mix by account")
            st.altair_chart(
                _build_account_mix_bar(mix, dark, hide_balances),
                width="stretch",
                key=f"allocation-{context_id}-account-mix-chart",
            )

    _render_sizing_guide(portfolio_summary.get("total_value") or 0.0, hide_balances)
