import streamlit as st

from frontend.services.streamlit_data import (
    create_transaction,
    load_single_security_quote,
)
from frontend.shared.dto import Currency, TransactionCreate, TransactionKind
from frontend.shared.settings import DEFAULT_TRADING_FEE, TRADE_SIZING_GUIDE


@st.dialog("Record Transaction", width="medium")
def transaction_form(
    account_id: str,
    account_name: str,
    portfolio_symbols: list[str] | None,
    fx_rate: float,
    portfolio_value: float,
    cash_balance: float,
    holdings_qty: dict[str, int] | None = None,
) -> TransactionCreate | None:
    st.subheader(f"Add Transaction to {account_name} Account")

    transaction_type = st.radio(
        "Transaction Type",
        TransactionKind,
        horizontal=True,
        key="transaction_type",
    )

    # --- Symbol selection (only for BUY / SELL) ---
    symbol: str | None = None
    if transaction_type == TransactionKind.BUY:
        symbol = st.selectbox(
            "Symbol",
            portfolio_symbols or [],
            index=None,
            accept_new_options=True,
            key="tx_symbol_buy",
        )
    elif transaction_type == TransactionKind.SELL:
        symbol = st.selectbox(
            "Symbol",
            portfolio_symbols or [],
            key="tx_symbol_sell",
        )

    # Defaults for quote-driven fields
    name: str = ""
    price_default: float = 0.0
    currency_default: Currency = Currency.CAD
    quantity_default: int = 0
    max_qty: int | None = None

    # --- Fetch quote for BUY / SELL once a symbol is chosen ---
    if transaction_type in (TransactionKind.BUY, TransactionKind.SELL):
        if not symbol:
            st.info("Enter or select a symbol to continue.")
            return None

        symbol = symbol.upper()
        quote = load_single_security_quote(symbol)
        if not quote:
            st.error(f"Security data for {symbol} not found")
            return None
        else:
            name = quote.get("name", "")
            price_default = float(quote.get("close", 0.0) or 0.0)
            raw_currency = quote.get("currency", "CAD")
            try:
                currency_default = Currency(raw_currency)
            except ValueError:
                currency_default = Currency.CAD

        if (
            portfolio_symbols is not None
            and symbol in portfolio_symbols
            and transaction_type == TransactionKind.SELL
        ):
            quantity_default = (holdings_qty or {}).get(symbol, 0)
            max_qty = quantity_default or None

        # -----------------------------------------------------------------
        # Reset quote-driven widget state when symbol changes
        # -----------------------------------------------------------------
        symbol_state_key = "tx_active_symbol"
        prev_symbol = st.session_state.get(symbol_state_key)

        if prev_symbol != symbol:
            st.session_state[symbol_state_key] = symbol
            st.session_state["tx_desc"] = name
            st.session_state["tx_price"] = price_default
            st.session_state["tx_qty"] = quantity_default
            st.session_state["tx_currency_trade"] = currency_default

    transaction_date = st.date_input(
        "Transaction Date",
        value="today",
        max_value="today",
        key="tx_date",
    )

    if transaction_type in (TransactionKind.BUY, TransactionKind.SELL):
        description = st.text_input("Description", key="tx_desc")
        c = st.columns(4)
        with c[0]:
            quantity = st.number_input(
                "Quantity",
                min_value=0,
                max_value=max_qty,
                key="tx_qty",
            )
        with c[1]:
            price = st.number_input("Price", min_value=0.0, key="tx_price")
        with c[2]:
            currency = st.radio(
                "Currency", Currency, horizontal=True, key="tx_currency_trade"
            )
        with c[3]:
            commission = st.number_input(
                "Commission",
                value=DEFAULT_TRADING_FEE,
                min_value=0.0,
                key="tx_commission",
            )
        flow = None
        value = None

    else:  # TransactionKind.EFT
        description = "EFT"
        quantity = 0
        price = 0.0
        commission = 0.0
        currency = st.radio(
            "Currency", Currency, horizontal=True, key="tx_currency_eft"
        )
        flow = st.radio(
            "Debit/Credit", ["Debit", "Credit"], horizontal=True, key="tx_flow"
        )
        value = st.number_input("Amount", value=0.0, min_value=0.0, key="tx_value")

    # ---------------------------------------------------------------------
    # Live preview at the base of the modal
    # ---------------------------------------------------------------------
    market = "US" if currency == Currency.USD else "CDN"
    exchange_rate = fx_rate if currency == Currency.USD else 1.0
    fees = commission * exchange_rate

    base_amount = 0.0
    amount = 0.0
    preview_label = "Preview"

    if transaction_type == TransactionKind.BUY:
        base_amount = float(price) * int(quantity) if quantity > 0 else 0.0
        amount = -(base_amount + float(commission)) * exchange_rate
        preview_label = "Buy (Debit)"

    elif transaction_type == TransactionKind.SELL:
        base_amount = float(price) * int(quantity) if quantity > 0 else 0.0
        amount = (base_amount - float(commission)) * exchange_rate
        preview_label = "Sell (Credit)"

    else:  # EFT
        v = float(value or 0.0)
        base_amount = v
        amount = v * exchange_rate if flow == "Credit" else -v * exchange_rate
        preview_label = "EFT (Credit)" if flow == "Credit" else "EFT (Debit)"

    st.divider()
    st.caption(preview_label)

    footer = st.columns([3, 3, 3, 1])
    with footer[0]:
        st.metric(
            label="Cash Available (CAD)",
            value=f"{cash_balance:,.2f}",
        )

    with footer[1]:
        st.metric(
            label=f"Base Amount ({currency})",
            value=f"{base_amount:,.2f}",
        )
    with footer[2]:
        st.metric(
            label=f"Booked Amount (CAD) @ FX {exchange_rate:.4f}",
            value=f"{abs(amount):,.2f}",
        )

    with footer[3]:
        with st.popover(
            icon=":material/info:",
            label="",
            help="Trade sizing guide",
        ):
            st.markdown(
                "**Based on current portfolio value:**\n"
                + "\n".join(
                    f"- **{k}**: ${v * portfolio_value:,.2f} CAD ({((v * portfolio_value) / (price * exchange_rate) if price > 0 and exchange_rate > 0 else 0):,.0f} shares)"
                    for k, v in TRADE_SIZING_GUIDE.items()
                )
            )

    # ---------------------------------------------------------------------
    # Submit (normal button)
    # ---------------------------------------------------------------------
    submit = st.button("Submit", type="primary")

    if not submit:
        return None

    # --- Guard: BUY must not exceed available cash balance ---
    if (
        transaction_type == TransactionKind.BUY
        and cash_balance > 0
        and abs(amount) > cash_balance
    ):
        st.toast(
            f"Insufficient funds — amount **{abs(amount):,.2f} CAD** exceeds available cash balance of **{cash_balance:,.2f} CAD**.",
            icon="🚫",
        )
        return None

    # --- Symbol cleaning (for records table) ---
    if transaction_type in (TransactionKind.BUY, TransactionKind.SELL):
        assert symbol is not None
        clean_symbol = symbol.replace(".TO", "") if symbol.endswith(".TO") else symbol
        clean_symbol = clean_symbol.replace("-", ".")
    else:
        clean_symbol = ""

    payload = TransactionCreate(
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        symbol=clean_symbol,
        market=market,
        description=description.upper(),
        quantity=quantity,
        currency=currency,
        price=price,
        commission=commission,
        exchange_rate=exchange_rate,
        fees_paid=fees,
        amount=amount,
    )

    create_transaction(account_id, payload)
    st.cache_data.clear()
    st.rerun()
