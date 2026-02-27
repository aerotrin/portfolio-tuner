import pandas as pd
import plotly.express as px
import streamlit as st


def render_portfolio_allocation(
    portfolio_summary: dict, df: pd.DataFrame | None
) -> None:
    """Allocation breakdown for current holdings."""
    df = df.copy() if df is not None else pd.DataFrame()

    st.markdown("#### :material/pie_chart: Allocation")

    if df.empty:
        st.info("No holdings found")
        return

    cash_value = portfolio_summary["cash_balance"]
    cash_weight = portfolio_summary["cash_pct"]
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
    cash_df = pd.DataFrame([cash_row])
    cash_df.index = ["CASH"]
    df = pd.concat([df, cash_df])

    cols = st.columns(2)
    with cols[0]:
        st.markdown("##### By Instrument")
        st.bar_chart(
            df,
            x="holding_category",
            y_label="Held as",
            y="market_value",
            x_label="Market Value CAD",
            color="symbol",
            horizontal=True,
        )

        st.markdown("##### By Currency")
        st.bar_chart(
            df,
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
            df,
            names="symbol",
            values="market_value",
            color="symbol",
            hover_data=["name"],
            height=450,
            hole=0.3,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig)
