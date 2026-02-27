import pandas as pd
import streamlit as st

from frontend.presentation.styles import (
    CASH_FLOWS_TABLE_CONFIG,
    CLOSED_LOTS_TABLE_CONFIG,
    TRANSACTIONS_TABLE_CONFIG,
    closed_lots_table_styler,
)
from frontend.services.streamlit_data import delete_transaction

BUY_SELL_TRANSACTIONS = {"Buy", "Purchase", "Sell", "Sold"}
CASH_TRANSACTIONS = {"Contrib", "Transf In", "EFT", "Transfer", "Withdrawal"}
INCOME_TRANSACTIONS = {"Dividend", "Interest"}
EXPENSE_TRANSACTIONS = {"Tax", "HST", "Fee"}


def get_date_filter_options(
    transactions: pd.DataFrame,
) -> dict[str, tuple[pd.Timestamp, pd.Timestamp | None]]:
    """Generate date filter options based on transaction history"""
    if transactions.empty or "transaction_date" not in transactions.columns:
        return {}

    # Ensure the transaction_date column is in datetime format
    transaction_dates = pd.to_datetime(
        transactions["transaction_date"], errors="coerce"
    )
    earliest_date = transaction_dates.min()
    current_year = pd.Timestamp.now().year
    earliest_year = earliest_date.year

    date_options = {
        "Year to date": (pd.Timestamp(f"{current_year}-01-01"), None),
        "Max available": (earliest_date, None),
    }

    for year in range(current_year - 1, earliest_year - 1, -1):
        date_options[str(year)] = (
            pd.Timestamp(f"{year}-01-01"),
            pd.Timestamp(f"{year}-12-31"),
        )

    return date_options


def render_records_header(
    transactions: pd.DataFrame | None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:

    header = st.columns([0.8, 0.2])
    with header[0]:
        st.markdown("#### :material/account_balance: Account Records")

    if transactions is None or transactions.empty:
        st.info("No transactions found")
        return None, None

    df = transactions.copy()
    date_options = get_date_filter_options(df)
    with header[1]:
        range_selection = st.selectbox(
            "Reporting Period",
            list(date_options.keys()),
            index=0,
            key="sel-report-date",
        )
    start_date, end_date = date_options[range_selection]
    return start_date, end_date


def render_closed_lots_table(
    closed_lots: pd.DataFrame,
    account_status: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp | None,
) -> None:

    if account_status == "Non-Registered":
        h = st.columns([4, 1])
        with h[0]:
            st.markdown("##### T5008 Statement of Securities Transactions")
        with h[1]:
            st.toggle(
                "Include expired options", value=True, key="include_expired_options"
            )
    else:
        st.markdown("##### Closed Positions")

    df = closed_lots.copy()
    if df.empty:
        st.info("No closed positions found.")
        return

    date_filter = df["close_date"] >= start_date
    if end_date:
        date_filter &= df["close_date"] <= end_date
    df_filtered = df[date_filter]

    if not st.session_state.get("include_expired_options", True):
        df_filtered = df_filtered[~df_filtered["is_expired"]]

    if not df_filtered.empty:
        summary = st.container(horizontal=True, border=True)
        with summary:
            st.metric("Book Value", f"${df_filtered['cost_basis'].sum():,.2f}")
            st.metric(
                "Proceeds of Disposition", f"${df_filtered['proceeds'].sum():,.2f}"
            )
            if account_status == "Non-Registered":
                st.metric(
                    "Total Capital Gain/Loss", f"${df_filtered['gain'].sum():,.2f}"
                )
            else:
                st.metric("Total Gain/Loss", f"${df_filtered['gain'].sum():,.2f}")
            st.metric("Number of Trades", f"{df_filtered.shape[0]:.0f}")
            st.metric("Average Days Held", f"{df_filtered['days_held'].mean():.0f}")
            st.metric(
                "Equity Gain/Loss",
                f"${df_filtered[(df_filtered['category'] == 'Equity')]['gain'].sum():,.2f}",
            )
            st.metric(
                "Options Gain/Loss",
                f"${df_filtered[(df_filtered['category'].isin(['Call Option', 'Put Option']))]['gain'].sum():,.2f}",
            )

        st.dataframe(
            closed_lots_table_styler(df_filtered),
            hide_index=True,
            column_order=CLOSED_LOTS_TABLE_CONFIG.keys(),
            column_config=CLOSED_LOTS_TABLE_CONFIG,
            key="table-closed-lots",
        )
    else:
        st.info("No closed positions found.")

    st.divider()


def render_cash_flows_table(
    cash_flows: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp | None
) -> None:
    st.markdown("##### Cash Flows")

    df = cash_flows.copy()
    if df.empty:
        st.info("No cash flows found.")
        return

    date_filter = df["transaction_date"] >= start_date
    if end_date:
        date_filter &= df["transaction_date"] <= end_date
    df_filtered = df[date_filter]

    if not df_filtered.empty:
        # --- Income / Expenses ------------------------------------------------------------------
        st.markdown("###### Income & Expenses")
        sub_df = df_filtered[
            df_filtered["transaction_type"].isin(
                list(INCOME_TRANSACTIONS) + list(EXPENSE_TRANSACTIONS)
            )
        ]

        if not sub_df.empty:
            summary = st.container(horizontal=True, border=True)
            with summary:
                st.metric(
                    "Gross Foreign Income (US)",
                    f"${sub_df[(sub_df['category'] == 'Income') & (sub_df['market'] != 'CDN')]['amount'].sum():,.2f}",
                )
                st.metric(
                    "Foreign Tax Paid (US)",
                    f"${-sub_df[(sub_df['transaction_type'] == 'Tax')]['amount'].sum():,.2f}",
                )
                st.metric(
                    "Canadian Dividends",
                    f"${sub_df[(sub_df['transaction_type'] == 'Dividend') & (sub_df['market'] == 'CDN')]['amount'].sum():,.2f}",
                )
                st.metric(
                    "Interest Income",
                    f"${sub_df[(sub_df['transaction_type'] == 'Interest')]['amount'].sum():,.2f}",
                )
                st.metric(
                    "Other Expenses",
                    f"${sub_df[(sub_df['category'] == 'Expense') & (sub_df['transaction_type'] != 'Tax')]['amount'].sum():,.2f}",
                )

            st.dataframe(
                sub_df,
                hide_index=True,
                column_order=CASH_FLOWS_TABLE_CONFIG.keys(),
                column_config=CASH_FLOWS_TABLE_CONFIG,
                key="table-income",
            )
        else:
            st.info("No income records found.")

        # --- Inflows/Outflows ------------------------------------------------------------------
        st.markdown("###### Inflows/Outflows")
        sub_df = df_filtered[df_filtered["transaction_type"].isin(CASH_TRANSACTIONS)]

        if not sub_df.empty:
            summary = st.container(horizontal=True, border=True)
            with summary:
                st.metric(
                    "Total Inflows",
                    f"${sub_df[sub_df['amount'] > 0]['amount'].sum():,.2f}",
                )
                st.metric(
                    "Total Outflows",
                    f"${-sub_df[sub_df['amount'] < 0]['amount'].sum():,.2f}",
                )
                st.metric(
                    "Net Investment",
                    f"${sub_df['amount'].sum():,.2f}",
                )

            st.dataframe(
                sub_df,
                hide_index=True,
                column_order=CASH_FLOWS_TABLE_CONFIG.keys(),
                column_config=CASH_FLOWS_TABLE_CONFIG,
                key="table-cash-flows",
            )
        else:
            st.info("No contributions found.")

    else:
        st.info("No cash flows found.")

    st.divider()


@st.dialog("Confirm deletion", width="small")
def confirm_delete_transaction_dialog(account_id: str, transaction_id: str) -> None:
    st.warning(
        "⚠️ This will permanently delete the transaction. This action cannot be undone."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cancel", width="stretch"):
            # Close dialog by rerunning without the pending delete
            st.session_state.pop("pending_delete_transaction_id", None)
            st.rerun()

    with col2:
        if st.button("Delete", type="primary", width="stretch"):
            msg = delete_transaction(account_id, transaction_id)
            if msg:
                st.error(msg)
            else:
                st.success("Transaction deleted.")
            st.cache_data.clear()
            st.session_state.pop("pending_delete_transaction_id", None)
            st.rerun()


def render_transactions_table(
    transactions: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp | None
) -> None:
    st.markdown("##### Transaction Records")

    df = transactions.copy()
    if df.empty:
        st.info("No transaction records found.")
        return

    date_filter = df["transaction_date"] >= start_date
    if end_date:
        date_filter &= df["transaction_date"] <= end_date
    df_filtered = df[date_filter]

    if not df_filtered.empty:
        sub_df = df_filtered[
            df_filtered["transaction_type"].isin(BUY_SELL_TRANSACTIONS)
        ]

        if not sub_df.empty:
            summary = st.container(horizontal=True, border=True)
            with summary:
                st.metric("Total Buys/Sells", f"{sub_df.shape[0]:.0f}")
                st.metric("Total Trading Fees", f"${sub_df['fees_paid'].sum():,.2f}")

        st.dataframe(
            df_filtered,
            hide_index=True,
            column_order=TRANSACTIONS_TABLE_CONFIG.keys(),
            column_config=TRANSACTIONS_TABLE_CONFIG,
            on_select="rerun",
            selection_mode="single-row",
            key="table-transactions-records",
        )
    else:
        st.info("No transaction records found.")

    # --- Delete Transaction ------------------------------------------------------------------
    delete_transaction_button = st.button(
        "Delete Transaction", icon=":material/delete:", type="secondary"
    )

    if delete_transaction_button:
        selected_row = (
            st.session_state.get("table-transactions-records", {})
            .get("selection", {})
            .get("rows", [])
        )

        if selected_row:
            selected_row_id = df_filtered.loc[selected_row[0], "id"]
            st.session_state["pending_delete_transaction_id"] = str(selected_row_id)
        else:
            st.error("No transaction selected")

    pending_id = st.session_state.get("pending_delete_transaction_id")
    if pending_id:
        confirm_delete_transaction_dialog(st.session_state["account_id"], pending_id)

    st.divider()
