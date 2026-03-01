import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


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


def render_correlation_matrix(matrix: pd.DataFrame | None = None) -> None:
    """Render correlation matrix for current holdings."""
    if matrix is None or matrix.empty:
        st.info("No correlation matrix found")
        return

    st.markdown("#### :material/ssid_chart: Correlation")

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
