import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.shared.dataframe import compute_correlation_matrix
from frontend.shared.settings import MIN_RETURN_OBS


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


def _excluded_note(excluded: list[str]) -> str:
    return (
        f"Not shown (fewer than {MIN_RETURN_OBS} days of price history): "
        + ", ".join(excluded)
        + "."
    )


def _fixed_income_note(fixed_income: list[str]) -> str:
    return "Not shown (fixed income, no market price): " + ", ".join(fixed_income) + "."


def _render_unavailable(
    excluded: list[str] | None, fixed_income: list[str] | None = None
) -> None:
    message = (
        "Not enough price history to compute correlations."
        if excluded
        else "Correlations need at least two market-priced holdings."
    )
    if excluded:
        message += " " + _excluded_note(excluded)
    if fixed_income:
        message += " " + _fixed_income_note(fixed_income)
    st.info(message)


def render_correlation_matrix(
    matrix: pd.DataFrame | None = None,
    excluded: list[str] | None = None,
    fixed_income: list[str] | None = None,
) -> None:
    """Render correlation matrix for current holdings; `excluded` names the
    symbols left out for too little price history and `fixed_income` the
    holdings that have no market price to correlate."""
    if (excluded or fixed_income) and (matrix is None or matrix.shape[0] < 2):
        _render_unavailable(excluded, fixed_income)
        return
    if matrix is None or matrix.empty:
        st.info("No correlation matrix found")
        return

    st.markdown("#### :material/ssid_chart: Correlation")
    if excluded:
        st.caption(f":material/info: {_excluded_note(excluded)}")
    if fixed_income:
        st.caption(f":material/info: {_fixed_income_note(fixed_income)}")

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
            height="content",
        )

        st.markdown("##### Weakest Correlation Pairs")
        st.dataframe(
            lowest,
            hide_index=True,
            height="content",
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


def render_market_correlation(closes: pd.DataFrame, symbols: list[str]) -> None:
    """Correlation view scoped to the Performance tab's group filter and row selection."""
    if len(symbols) < 2:
        st.info(
            "Select at least two securities via the Performance tab's group filter "
            "or table selection to compute correlations."
        )
        return

    matrix, excluded = compute_correlation_matrix(closes, symbols)
    if matrix.shape[0] < 2:
        _render_unavailable(excluded)
        return

    render_correlation_matrix(matrix, excluded)
    st.caption(
        "Daily-return correlation, trailing 252 trading days. "
        "Scope follows the Performance tab's group filter and row selection."
    )
