import pandas as pd
from pandas.io.formats.style import Styler
import streamlit as st

from src.presentation.settings import (
    GREEN,
    GREEN_BG,
    LOSS_LIMIT,
    NO_STYLE,
    RED,
    RED_BG,
    SPARKLINE_WIDTH,
    TAKE_PROFIT_LIMIT,
)


QUOTE_TABLE_CONFIG = {
    "symbol": st.column_config.TextColumn("Symbol"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    "close": st.column_config.NumberColumn("Last", format="accounting"),
    "change": st.column_config.NumberColumn("Change", format="%+.2f"),
    "changePercent": st.column_config.NumberColumn("Change %", format="percent"),
    "volume": st.column_config.NumberColumn("Volume", format="compact"),
    "previousClose": st.column_config.NumberColumn("Prev. Close", format="accounting"),
    "open": st.column_config.NumberColumn("Open", format="accounting"),
    "high": st.column_config.NumberColumn("High", format="accounting"),
    "low": st.column_config.NumberColumn("Low", format="accounting"),
    "exchange": st.column_config.TextColumn("Exchange"),
    # "currency": st.column_config.TextColumn("Currency"),
    "timestamp": st.column_config.DatetimeColumn("Last Trade", format="distance"),
}


def quote_table_styler(df: pd.DataFrame) -> Styler:
    VALUE_COLS = [
        "change",
        "changePercent",
    ]

    def style_row(row):
        change = row["change"]
        if pd.isna(change):
            color = NO_STYLE
        elif change >= 0:
            color = f"color: {GREEN};"
        elif change < 0:
            color = f"color: {RED};"
        else:
            color = NO_STYLE

        style = pd.Series(NO_STYLE, index=df.columns)
        for col in VALUE_COLS:
            if col in style.index:
                style[col] = color
        return style

    return df.style.apply(style_row, axis=1)


POSITIONS_TABLE_CONFIG = {
    "symbol": st.column_config.TextColumn("Symbol"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "open_qty": st.column_config.NumberColumn("Quantity", format="compact"),
    "weight": st.column_config.NumberColumn("Weight %", format="percent"),
    "days_held": st.column_config.NumberColumn("Days Held", format="compact"),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    "close": st.column_config.NumberColumn("Last", format="accounting"),
    "breakeven_price": st.column_config.NumberColumn("B/E Price", format="accounting"),
    "currency": st.column_config.TextColumn("Currency"),
    "changePercent": st.column_config.NumberColumn("Day %", format="percent"),
    "intraday_gain": st.column_config.NumberColumn("Day P/L CAD", format="dollar"),
    "gain": st.column_config.NumberColumn("Total P/L CAD", format="dollar"),
    "gain_pct": st.column_config.NumberColumn("Total P/L %", format="percent"),
    "market_value": st.column_config.NumberColumn("Mkt Value CAD", format="dollar"),
    "book_value": st.column_config.NumberColumn("Book Value CAD", format="dollar"),
    "fx_exposure": st.column_config.NumberColumn("FX Exposure", format="dollar"),
    # "intraday_contribution": st.column_config.NumberColumn(
    #     "Day P/L Contrib. %", format="percent"
    # ),
    # "pnl_contribution": st.column_config.NumberColumn(
    #     "P/L Contrib. %", format="percent"
    # ),
    # "distance_to_breakeven": st.column_config.NumberColumn(
    #     "B/E Dist %", format="percent"
    # ),
    "security_type": st.column_config.TextColumn("Type"),
    "option_osi": st.column_config.TextColumn("Option OSI"),
    "option_strike": st.column_config.NumberColumn("Option Strike", format="%.3f"),
    "option_expiry": st.column_config.DateColumn("Option Expiry", format="YYYY-MM-DD"),
    "option_dte": st.column_config.NumberColumn("Option DTE", format="%.3f"),
    # "acb_per_sh": st.column_config.NumberColumn("Unit ACB CAD", format="accounting"),
    # "fx_rate": st.column_config.NumberColumn("FX Rate", format="%.3f"),
    "open_date": st.column_config.DateColumn("Open Date", format="YYYY-MM-DD"),
    "timestamp": st.column_config.DatetimeColumn("Last Trade", format="distance"),
    "last_updated": st.column_config.DatetimeColumn("Last Updated", format="localized"),
}


def positions_table_styler(df: pd.DataFrame) -> Styler:
    VALUE_COLS = [
        "changePercent",
        "intraday_gain",
    ]

    POSITION_COLS = [
        "market_value",
        "gain",
        "gain_pct",
    ]

    def style_row(row):
        gain_pct = row["gain_pct"]

        # --- Row background based on profit / loss thresholds ---
        if pd.isna(gain_pct):
            row_bg = ""
        elif gain_pct >= TAKE_PROFIT_LIMIT:
            row_bg = f"background-color: {GREEN_BG};"
        elif gain_pct <= LOSS_LIMIT:
            row_bg = f"background-color: {RED_BG};"
        else:
            row_bg = ""

        # start with background for entire row
        style = pd.Series(row_bg, index=df.columns)

        # --- Text color based on sign of gain ---
        gain = row["gain"]
        if not pd.isna(gain):
            if gain > 0:
                color = f"color: {GREEN};"
            elif gain < 0:
                color = f"color: {RED};"
            else:
                color = ""

            if color:
                for col in POSITION_COLS:
                    if col in style.index:
                        style[col] = f"{row_bg} {color}".strip()

        for col in VALUE_COLS:
            if col in style.index:
                val = row[col]
                if pd.isna(val):
                    continue
                if val > 0:
                    style[col] = f"{row_bg} color: {GREEN}".strip()
                elif val < 0:
                    style[col] = f"{row_bg} color: {RED}".strip()
                else:
                    style[col] = row_bg

        return style

    return df.style.apply(style_row, axis=1)


PERFORMANCE_TABLE_CONFIG = {
    "symbol": st.column_config.TextColumn("Symbol"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "trend": st.column_config.ProgressColumn(
        "Trend 5D",
        format=" ",
        min_value=-1.0,
        max_value=1.0,
        width="small",
        color="auto",
    ),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    "return5D": st.column_config.NumberColumn("Return 5D", format="percent"),
    "return1M": st.column_config.NumberColumn("Return 1M", format="percent"),
    "return3M": st.column_config.NumberColumn("Return 3M", format="percent"),
    "return6M": st.column_config.NumberColumn("Return 6M", format="percent"),
    "return1Y": st.column_config.NumberColumn("Return 1Y", format="percent"),
    "volatility": st.column_config.NumberColumn("Volatility", format="percent"),
    "sharpe": st.column_config.NumberColumn("Sharpe", format="%.3f"),
    "sortino": st.column_config.NumberColumn("Sortino", format="%.3f"),
    "max_drawdown": st.column_config.NumberColumn("MDD", format="percent"),
    "max_drawdown_date": st.column_config.DateColumn("MDD Date", format="YYYY-MM-DD"),
    "exchange": st.column_config.TextColumn("Exchange"),
    "currency": st.column_config.TextColumn("Currency"),
    "last_updated": st.column_config.DatetimeColumn("Last Updated"),
    # "type": st.column_config.TextColumn("Type"),
    # "marketCap": st.column_config.NumberColumn("Market Cap", format="compact"),
    # "beta": st.column_config.NumberColumn("Beta", format="%.3f"),
    # "lastDividend": st.column_config.NumberColumn("Last Dividend", format="accounting"),
    # "averageVolume": st.column_config.NumberColumn("Avg Volume", format="compact"),
    # "yearHigh": st.column_config.NumberColumn("52 Wk High", format="accounting"),
    # "yearLow": st.column_config.NumberColumn("52 Wk Low", format="accounting"),
    # "country": st.column_config.TextColumn("Country"),
    # "sector": st.column_config.TextColumn("Sector"),
    # "industry": st.column_config.TextColumn("Industry"),
    # "isin": st.column_config.TextColumn("ISIN"),
    # "cusip": st.column_config.TextColumn("CUSIP"),
}


def performance_table_styler(df: pd.DataFrame) -> Styler:
    RETURN_COLS = ["return5D", "return1M", "return3M", "return6M", "return1Y"]

    def style_row(row):
        # --- Row background rules ---
        if row["near_52wk_hi"]:
            row_bg = f"background-color: {GREEN_BG};"
        elif row["near_52wk_lo"]:
            row_bg = f"background-color: {RED_BG};"
        else:
            row_bg = ""

        # base style for entire row
        style = pd.Series(row_bg, index=df.columns)

        # --- Cell-level return coloring ---
        for col in RETURN_COLS:
            if col in style.index:
                val = row[col]
                if pd.isna(val):
                    continue
                if val > 0:
                    style[col] = f"{row_bg} color: {GREEN}".strip()
                elif val < 0:
                    style[col] = f"{row_bg} color: {RED}".strip()
                else:
                    style[col] = row_bg

        return style

    return df.style.apply(style_row, axis=1)


TRANSACTIONS_TABLE_CONFIG = {
    "transaction_date": st.column_config.DateColumn(
        "Transaction Date", format="YYYY-MM-DD"
    ),
    "settlement_date": st.column_config.DateColumn(
        "Settlement Date", format="YYYY-MM-DD"
    ),
    "transaction_type": st.column_config.TextColumn("Type"),
    "symbol": st.column_config.TextColumn("Symbol"),
    "market": st.column_config.TextColumn("Market"),
    "description": st.column_config.TextColumn("Description"),
    "quantity": st.column_config.NumberColumn("Quantity", format="compact"),
    "currency": st.column_config.TextColumn("Currency"),
    "price": st.column_config.NumberColumn("Price", format="accounting"),
    "commission": st.column_config.NumberColumn("Commission", format="accounting"),
    "exchange_rate": st.column_config.NumberColumn("Exchange Rate", format="%.3f"),
    "fees_paid": st.column_config.NumberColumn("Fees", format="accounting"),
    "amount": st.column_config.NumberColumn("Amount", format="accounting"),
    "timestamp": st.column_config.DatetimeColumn("Last Updated", format="localized"),
}

CLOSED_LOTS_TABLE_CONFIG = {
    "close_date": st.column_config.DateColumn("Close Date", format="YYYY-MM-DD"),
    "category": st.column_config.TextColumn("Category"),
    "transaction_type": st.column_config.TextColumn("Type"),
    "symbol": st.column_config.TextColumn("Symbol"),
    "option_osi": st.column_config.TextColumn("Option OSI"),
    "description": st.column_config.TextColumn("Description"),
    "close_qty": st.column_config.NumberColumn("Quantity", format="compact"),
    "price": st.column_config.NumberColumn("Price", format="accounting"),
    "currency": st.column_config.TextColumn("Currency"),
    "proceeds": st.column_config.NumberColumn("Proceeds", format="accounting"),
    "cost_basis": st.column_config.NumberColumn("Cost Basis", format="accounting"),
    "gain": st.column_config.NumberColumn("Gain", format="accounting"),
    "gain_pct": st.column_config.NumberColumn("Gain %", format="percent"),
    "last_open_date": st.column_config.DateColumn(
        "Last Open Date", format="YYYY-MM-DD"
    ),
    "days_held": st.column_config.NumberColumn("Days Held", format="compact"),
    "option_expiry": st.column_config.DateColumn("Option Expiry", format="YYYY-MM-DD"),
    "is_expired": st.column_config.CheckboxColumn("Option Expired"),
}


def closed_lots_table_styler(df: pd.DataFrame) -> Styler:
    VALUE_COLS = [
        "gain",
        "gain_pct",
    ]

    def style_row(row):
        gain = row["gain"]

        # --- Row background based on gain / loss ---
        if pd.isna(gain):
            row_bg = ""
        elif gain > 0:
            row_bg = f"background-color: {GREEN_BG};"
        elif gain < 0:
            row_bg = f"background-color: {RED_BG};"
        else:
            row_bg = ""

        # start with background for entire row
        style = pd.Series(row_bg, index=df.columns)

        # --- Text color based on sign of gain ---
        if not pd.isna(gain):
            if gain > 0:
                color = f"color: {GREEN};"
            elif gain < 0:
                color = f"color: {RED};"
            else:
                color = ""

            if color:
                for col in VALUE_COLS:
                    if col in style.index:
                        style[col] = f"{row_bg} {color}".strip()

        return style

    return df.style.apply(style_row, axis=1)


CASH_FLOWS_TABLE_CONFIG = {
    "transaction_date": st.column_config.DateColumn(
        "Transaction Date", format="YYYY-MM-DD"
    ),
    "settlement_date": st.column_config.DateColumn(
        "Settlement Date", format="YYYY-MM-DD"
    ),
    "category": st.column_config.TextColumn("Category"),
    "transaction_type": st.column_config.TextColumn("Type"),
    "market": st.column_config.TextColumn("Market"),
    "description": st.column_config.TextColumn("Description"),
    # "quantity": st.column_config.NumberColumn("Quantity", format="compact"),
    "currency": st.column_config.TextColumn("Currency"),
    "amount": st.column_config.NumberColumn("Amount", format="accounting"),
}
