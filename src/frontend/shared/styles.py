import pandas as pd
from pandas.io.formats.style import Styler
import streamlit as st

from frontend.shared.settings import (
    GREEN,
    GREEN_BG,
    LOSS_LIMIT,
    NO_STYLE,
    RED,
    RED_BG,
    SPARKLINE_WIDTH,
    TAKE_PROFIT_LIMIT,
)

SIGNAL_HELP = (
    "●●● = Strong | ●●○ = MACD > 0 | ●○○ = RSI > 50 + up trend | "
    "⚠ = RSI > 70 (overbought) | ▽ = RSI < 30 (oversold)"
)

PRICE_HELP = "In the security's own currency; green or red by today's move."
DAY_HELP = "Change since the previous close."

# Columns that reveal account size — dropped from tables when Hide Balances is on
BALANCE_COLUMNS = (
    "open_qty",
    "intraday_change",
    "market_value",
    "gain",
    "book_value",
    "fx_exposure",
    "option_value",
    "cash_balance",
    "cash_balance_native",
    "fi_principal",
    "fi_accrued_interest",
    "fi_interest_received",
    "fi_maturity_value",
)


def balance_safe_column_order(config: dict, hide_balances: bool) -> list[str]:
    if not hide_balances:
        return list(config)
    return [c for c in config if c not in BALANCE_COLUMNS]


def with_account_column(config: dict, after: str) -> dict:
    """Return a copy of a table config with an Account column after `after`."""
    result = {}
    for key, col in config.items():
        result[key] = col
        if key == after:
            result["account"] = st.column_config.TextColumn("Account")
    return result


QUOTE_TABLE_CONFIG = {
    "symbol": st.column_config.TextColumn("Symbol"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    # Price and Day carry no format: the table stylers supply their text
    "close": st.column_config.NumberColumn("Price", help=PRICE_HELP),
    "change_percent": st.column_config.NumberColumn("Day", help=DAY_HELP),
    "signal": st.column_config.TextColumn("Signal", help=SIGNAL_HELP),
    "return5D": st.column_config.NumberColumn("Chg 5D", format="percent"),
    "return1M": st.column_config.NumberColumn("Chg 1M", format="percent"),
    "rsi": st.column_config.NumberColumn("RSI", format="%.0f"),
    "volume": st.column_config.NumberColumn("Volume", format="compact"),
    "relative_volume": st.column_config.NumberColumn(
        "Rel Vol", format="%.1f×", help="Today's volume ÷ 20-day average volume"
    ),
    "dollar_volume": st.column_config.NumberColumn(
        "$ Vol",
        format="compact",
        help="Today's volume × price, in the security's own currency",
    ),
    # "open": st.column_config.NumberColumn("Open", format="accounting"),
    "previousClose": st.column_config.NumberColumn("Last Close", format="accounting"),
    "high": st.column_config.NumberColumn("High", format="accounting"),
    "low": st.column_config.NumberColumn("Low", format="accounting"),
    "volatility": st.column_config.NumberColumn("Volatility", format="percent"),
    "exchange": st.column_config.TextColumn("Exchange"),
    "timestamp": st.column_config.DatetimeColumn("Last Trade", format="distance"),
}


def quote_table_styler(df: pd.DataFrame) -> Styler:
    VALUE_COLS = ["change", "change_percent", "return5D", "return1M"]

    def style_row(row):
        style = pd.Series(NO_STYLE, index=df.columns)

        for col in VALUE_COLS:
            if col not in style.index:
                continue
            val = row[col]
            if pd.isna(val):
                continue
            if val > 0:
                style[col] = f"color: {GREEN};"
            elif val < 0:
                style[col] = f"color: {RED};"

        # RSI coloring
        rsi = row.get("rsi")
        if "rsi" in style.index and not pd.isna(rsi):
            if rsi > 70:
                style["rsi"] = f"color: {RED};"
            elif rsi < 30:
                style["rsi"] = f"color: {GREEN};"

        if "close" in style.index and "change_percent" in style.index:
            style["close"] = style["change_percent"]

        return style

    return _format_price_and_day(df.style.apply(style_row, axis=1), df)


POSITIONS_EQUITY_TABLE_CONFIG = {
    "symbol": st.column_config.TextColumn("Symbol"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    # Price and Day carry no format: positions_table_styler supplies their text
    "close": st.column_config.NumberColumn("Price", help=PRICE_HELP),
    "change_percent": st.column_config.NumberColumn("Day", help=DAY_HELP),
    "signal": st.column_config.TextColumn("Signal", help=SIGNAL_HELP),
    "relative_volume": st.column_config.NumberColumn(
        "Rel Vol", format="%.1f×", help="Today's volume ÷ 20-day average volume"
    ),
    "intraday_change": st.column_config.NumberColumn("Day P/L CAD", format="dollar"),
    "gain": st.column_config.NumberColumn("Total P/L CAD", format="dollar"),
    "gain_pct": st.column_config.NumberColumn("Total P/L %", format="percent"),
    "market_value": st.column_config.NumberColumn("Mkt Value CAD", format="dollar"),
    "weight": st.column_config.NumberColumn("Weight %", format="percent"),
    "open_qty": st.column_config.NumberColumn("Quantity", format="compact"),
    "days_held": st.column_config.NumberColumn("Days", format="compact"),
    "breakeven_price": st.column_config.NumberColumn("B/E Price", format="accounting"),
    "book_value": st.column_config.NumberColumn("Book Value CAD", format="dollar"),
    "fx_exposure": st.column_config.NumberColumn("FX Exposure", format="dollar"),
    "security_type": st.column_config.TextColumn("Type"),
    "open_date": st.column_config.DateColumn("Open Date", format="YYYY-MM-DD"),
    "timestamp": st.column_config.DatetimeColumn("Last Trade", format="distance"),
    "last_updated": st.column_config.DatetimeColumn("Last Updated", format="localized"),
}


POSITIONS_OPTION_TABLE_CONFIG = {
    "option_osi": st.column_config.TextColumn("OSI"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    "close": st.column_config.NumberColumn(
        "Underlying", help="Latest price of the underlying. " + PRICE_HELP
    ),
    "change_percent": st.column_config.NumberColumn(
        "Und. Day", help="The underlying's change today. " + DAY_HELP
    ),
    "holding_category": st.column_config.TextColumn("Right"),
    "option_dte": st.column_config.NumberColumn("DTE", format="compact"),
    "option_value": st.column_config.NumberColumn(
        "Intrinsic Value ⚠️", format="accounting"
    ),
    "gain": st.column_config.NumberColumn("Total P/L CAD", format="dollar"),
    "gain_pct": st.column_config.NumberColumn("Total P/L %", format="percent"),
    "market_value": st.column_config.NumberColumn("Mkt Value CAD", format="dollar"),
    "weight": st.column_config.NumberColumn("Weight %", format="percent"),
    "open_qty": st.column_config.NumberColumn("Quantity", format="compact"),
    "breakeven_price": st.column_config.NumberColumn("B/E Price", format="accounting"),
    "book_value": st.column_config.NumberColumn("Book Value CAD", format="dollar"),
    "option_expiry": st.column_config.DateColumn("Expiry", format="YYYY-MM-DD"),
    "option_strike": st.column_config.NumberColumn("Strike", format="accounting"),
    "fx_exposure": st.column_config.NumberColumn("FX Exposure", format="dollar"),
    "days_held": st.column_config.NumberColumn("Days Held", format="compact"),
    "security_type": st.column_config.TextColumn("Type"),
    "open_date": st.column_config.DateColumn("Open Date", format="YYYY-MM-DD"),
    "timestamp": st.column_config.DatetimeColumn("Last Trade", format="distance"),
    "last_updated": st.column_config.DatetimeColumn("Last Updated", format="localized"),
}


POSITIONS_FIXED_INCOME_TABLE_CONFIG = {
    "name": st.column_config.TextColumn("Name", width="medium"),
    "fi_status": st.column_config.TextColumn("Status"),
    "fi_rate": st.column_config.NumberColumn("Rate", format="percent"),
    "fi_payment_frequency": st.column_config.TextColumn("Interest Paid"),
    "weight": st.column_config.NumberColumn("Weight %", format="percent"),
    "fi_principal": st.column_config.NumberColumn("Principal", format="accounting"),
    "currency": st.column_config.TextColumn("Currency"),
    "fi_maturity_date": st.column_config.DateColumn("Maturity", format="YYYY-MM-DD"),
    "fi_days_to_maturity": st.column_config.NumberColumn(
        "Days to Maturity", format="compact"
    ),
    "fi_accrued_interest": st.column_config.NumberColumn(
        "Accrued Interest",
        format="accounting",
        help="Interest earned to date that has not been paid out yet",
    ),
    "fi_interest_received": st.column_config.NumberColumn(
        "Interest Received", format="accounting"
    ),
    "market_value": st.column_config.NumberColumn(
        "Value CAD", format="dollar", help="Principal plus accrued interest"
    ),
    "fi_maturity_value": st.column_config.NumberColumn(
        "Maturity Value",
        format="accounting",
        help="Principal plus all interest over the term",
    ),
    "gain": st.column_config.NumberColumn("Total P/L CAD", format="dollar"),
    "gain_pct": st.column_config.NumberColumn("Total P/L %", format="percent"),
    "book_value": st.column_config.NumberColumn("Book Value CAD", format="dollar"),
    "fx_exposure": st.column_config.NumberColumn("FX Exposure", format="dollar"),
    "fi_issue_date": st.column_config.DateColumn("Issue Date", format="YYYY-MM-DD"),
    "days_held": st.column_config.NumberColumn("Days Held", format="compact"),
    "security_type": st.column_config.TextColumn("Type"),
    "symbol": st.column_config.TextColumn("Key"),
}


POSITIONS_CASH_TABLE_CONFIG = {
    "label": st.column_config.TextColumn("Account"),
    "currency": st.column_config.TextColumn("Currency"),
    "cash_balance_native": st.column_config.NumberColumn("Cash", format="accounting"),
    "cash_balance": st.column_config.NumberColumn("Cash CAD", format="dollar"),
    "account_cash_pct": st.column_config.NumberColumn("% of Account", format="percent"),
    "weight": st.column_config.NumberColumn(
        "Weight %", format="percent", help="Share of the portfolio's total value"
    ),
}


def cash_table_styler(df: pd.DataFrame) -> Styler:
    """Negative cash (margin / overdraft) in red."""
    cash_cols = [c for c in ("cash_balance_native", "cash_balance") if c in df]
    return df.style.map(
        lambda v: f"color: {RED}" if pd.notna(v) and v < 0 else "",
        subset=cash_cols,
    )


def _day_change_text(value: float) -> str:
    """0.0414 -> "▲ 4.14%", -0.0414 -> "▼ 4.14%"; a dash before any change
    is published (premarket)."""
    if pd.isna(value):
        return "—"
    arrow = "▲ " if value > 0 else "▼ " if value < 0 else ""
    return f"{arrow}{abs(value):.2%}"


def _format_price_and_day(styler: Styler, df: pd.DataFrame) -> Styler:
    """Display text for the Price and Day columns: "611.68 USD" and "▼ 4.14%".
    Both stay numeric underneath, so they sort as numbers; the currency and
    the arrow are display only."""
    if "change_percent" in df.columns:
        styler = styler.format(_day_change_text, subset=["change_percent"])
    if "close" in df.columns:
        styler = styler.format("{:,.2f}", subset=["close"], na_rep="")
        if "currency" in df.columns:
            # A formatter sees only the cell, so each currency gets its own
            for currency in df["currency"].dropna().unique():
                rows = df.index[(df["currency"] == currency) & df["close"].notna()]
                styler = styler.format(
                    f"{{:,.2f}} {currency}", subset=pd.IndexSlice[rows, ["close"]]
                )
    return styler


def positions_table_styler(df: pd.DataFrame) -> Styler:
    """Row shading, gain/loss colours, and Price and Day coloured by today's
    move and shown as text by `_format_price_and_day`."""
    VALUE_COLS = [
        "change",
        "change_percent",
        "intraday_change",
    ]

    POSITION_COLS = [
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

        if "close" in style.index and "change_percent" in style.index:
            style["close"] = style["change_percent"]

        return style

    return _format_price_and_day(df.style.apply(style_row, axis=1), df)


PERFORMANCE_TABLE_CONFIG = {
    "symbol": st.column_config.TextColumn("Symbol"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sparkline": st.column_config.AreaChartColumn(
        "Price (1Y)", width=SPARKLINE_WIDTH, color="auto"
    ),
    "weight": st.column_config.NumberColumn("Weight", format="percent"),
    "close": st.column_config.NumberColumn("Price", help=PRICE_HELP),
    "change_percent": st.column_config.NumberColumn("Day", help=DAY_HELP),
    "signal": st.column_config.TextColumn("Signal", help=SIGNAL_HELP),
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
    "last_calculated": st.column_config.DatetimeColumn("Last Computed"),
}


def performance_table_styler(df: pd.DataFrame) -> Styler:
    VALUE_COLS = [
        "change_percent",
        "return5D",
        "return1M",
        "return3M",
        "return6M",
        "return1Y",
    ]

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

        # RSI coloring
        rsi = row["rsi"]
        if not pd.isna(rsi):
            if rsi > 70:
                style["rsi"] = f"{row_bg} color: {RED}".strip()
            elif rsi < 30:
                style["rsi"] = f"{row_bg} color: {GREEN}".strip()
            else:
                style["rsi"] = row_bg

        if "close" in style.index and "change_percent" in style.index:
            style["close"] = style["change_percent"]

        return style

    return _format_price_and_day(df.style.apply(style_row, axis=1), df)


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
    "symbol": st.column_config.TextColumn("Symbol"),
    "market": st.column_config.TextColumn("Market"),
    "description": st.column_config.TextColumn("Description"),
    "currency": st.column_config.TextColumn("Currency"),
    "amount": st.column_config.NumberColumn("Amount", format="accounting"),
}
