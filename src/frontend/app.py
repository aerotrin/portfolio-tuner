from datetime import datetime, timedelta
import logging

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from supabase import create_client

from frontend.services.streamlit_data import (
    delete_account,
    get_api_client,
    import_account_records,
    load_accounts_list,
    load_rates,
)
from frontend.shared.symbols_loader import load_symbols_config
from frontend.shared.env_loader import config
from frontend.shared.jobs import start_refresh_job
from frontend.shared.logging import setup_logging
from frontend.widgets.account_dialogs import create_account_dialog, edit_account_dialog
from frontend.widgets.transaction_form import transaction_form

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
setup_logging(config.log_level)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Page config
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Portfolio Dashboard",
    layout="wide",
    page_icon=":bar_chart:",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Styling helpers
# -----------------------------------------------------------------------------
def apply_compact_css() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 3rem;
                padding-bottom: 1rem;
                padding-left: 2rem;
                padding-right: 2rem;
                max-width: 1200px;
            }

            div[data-testid="stMetricLabel"] {
                font-size: 14px;
            }

            div[data-testid="stMetricValue"] {
                font-size: 16px;
                font-weight: bold;
            }

            div[data-testid="stMetricDelta"] {
                font-size: 12px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_compact_css()


# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------
def _get_supabase_client():
    if "supabase" not in st.session_state:
        st.session_state["supabase"] = create_client(
            config.supabase_url, config.supabase_key
        )
    return st.session_state["supabase"]


def _show_login() -> None:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("Portfolio Tuner")
        st.subheader("Sign In")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Sign In", type="primary", width="stretch"
            )
        if submitted:
            try:
                sb = _get_supabase_client()
                res = sb.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
                st.session_state["jwt_token"] = res.session.access_token
                st.session_state["user_id"] = res.user.id
                st.session_state["authenticated"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"Login failed: {exc}")


if not st.session_state.get("authenticated"):
    _show_login()
    st.stop()

# Sync the current access token on every rerun so token rotation is picked up.
# gotrue refreshes the token internally; get_session() returns the live token.
_current_session = _get_supabase_client().auth.get_session()
if _current_session:
    st.session_state["jwt_token"] = _current_session.access_token
    st.session_state["user_id"] = _current_session.user.id
else:
    # Session has fully expired — force re-login
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# -----------------------------------------------------------------------------
# Disclaimer
# -----------------------------------------------------------------------------
DISCLAIMER_SHORT = """
**Portfolio Tuner is for informational and educational purposes only and does not provide financial, investment, tax, or legal advice.**
It is not a regulated financial product. Data and analytics may be inaccurate or incomplete.
All decisions are made at your own risk. The authors disclaim liability for losses arising from use of the software.
"""


@st.dialog("Disclaimer")
def show_disclaimer_dialog() -> None:
    st.markdown(DISCLAIMER_SHORT)
    st.caption("You can view the full disclaimer in the About / Legal section.")
    if st.button("I Understand", type="primary"):
        st.session_state["disclaimer_accepted"] = True
        st.rerun()


st.session_state.setdefault("disclaimer_accepted", False)
if not st.session_state["disclaimer_accepted"]:
    show_disclaimer_dialog()
    st.stop()

# -----------------------------------------------------------------------------
# Navigation
# -----------------------------------------------------------------------------
pages = [
    st.Page(page="pages/1_Market_ETFs.py", title="🏦 ETF Research", default=False),
    st.Page(page="pages/2_Market_Stocks.py", title="🏦 Stocks Research", default=False),
    st.Page(page="pages/3_Portfolios.py", title="📊 Portfolios", default=True),
    st.Page(page="pages/9_About.py", title="ℹ️ About", default=False),
]
pg = st.navigation(pages)

# -----------------------------------------------------------------------------
# Session bootstrap
# -----------------------------------------------------------------------------
BOOT_VERSION = 1  # bump this if you change bootstrap semantics


def bootstrap_once() -> None:
    """
    Set stable defaults and derived (config-based) symbol sets exactly once per session.
    Avoid rewriting session_state on every rerun.
    """
    if st.session_state.get("_boot_version") == BOOT_VERSION:
        return

    # --- Stable UI defaults ---
    st.session_state.setdefault("hide_balances_toggle", False)
    st.session_state.setdefault("live_data_toggle", False)
    st.session_state.setdefault("show_session_state_toggle", False)

    # --- Date range defaults (only if missing) ---
    if "start_date" not in st.session_state or "end_date" not in st.session_state:
        now = datetime.now()
        st.session_state["start_date"] = (now - timedelta(days=365)).strftime(
            "%Y-%m-%d"
        )
        st.session_state["end_date"] = now.strftime("%Y-%m-%d")

    # --- Load symbols config once and derive symbol sets once ---
    symbols_config = load_symbols_config()
    header_symbols = symbols_config.snapshot.symbols
    benchmark_symbols = symbols_config.benchmarks.symbols
    base_symbols = sorted(
        {
            *header_symbols,
            *benchmark_symbols,
        }
    )
    st.session_state["header_symbols"] = header_symbols
    st.session_state["benchmark_symbols"] = benchmark_symbols
    st.session_state["base_symbols"] = base_symbols

    market_etf_symbols = sorted(
        {
            symbol
            for group in symbols_config.base_market_etfs
            for symbol in group.symbols
        }
    )

    market_stock_symbols = sorted(
        {
            symbol
            for group in symbols_config.base_market_stocks
            for symbol in group.symbols
        }
    )

    market_symbols = sorted({*market_etf_symbols, *market_stock_symbols})

    st.session_state["market_etf_symbols"] = market_etf_symbols
    st.session_state["market_stock_symbols"] = market_stock_symbols
    st.session_state["market_symbols"] = market_symbols

    # Dialog flags
    st.session_state.setdefault("show_create_account_dialog", False)
    st.session_state.setdefault("show_edit_account_dialog", False)
    st.session_state.setdefault("show_import_records_dialog", False)
    st.session_state.setdefault("show_delete_account_confirm", False)
    st.session_state.setdefault("show_transaction_form_dialog", False)

    # Mark boot complete
    st.session_state["_boot_version"] = BOOT_VERSION


bootstrap_once()

# -----------------------------------------------------------------------------
# Auto-refresh
# -----------------------------------------------------------------------------
if config.app_refresh_interval and config.app_refresh_interval > 0:
    st_autorefresh(interval=config.app_refresh_interval, key="app_autorefresh")

# -----------------------------------------------------------------------------
# Services
# -----------------------------------------------------------------------------
api = get_api_client()


# -----------------------------------------------------------------------------
# Cached boot data (API calls)
# -----------------------------------------------------------------------------

# Load accounts for sidebar selection; keep expensive loads lazy.
accounts = load_accounts_list(st.session_state["user_id"])

# Load cached data to session state
st.session_state["rates"] = load_rates()

# Benchmarks from bootstrap
benchmark_symbols = st.session_state.get("benchmark_symbols", [])
header_symbols = st.session_state.get("header_symbols", [])
market_symbols = st.session_state.get("market_symbols", [])

# -----------------------------------------------------------------------------
# Account gating (still done before rendering pages)
# -----------------------------------------------------------------------------
if not accounts:
    st.warning("No accounts found — create a new account")
    create_account_dialog(benchmark_symbols)
    st.stop()

account_numbers = [account.number for account in accounts]
account_display_labels = [f"{account.type} #{account.number}" for account in accounts]
account_ids = [account.id for account in accounts]

# Choose default account only if not set
st.session_state.setdefault("account_display_label", account_display_labels[0])


# -----------------------------------------------------------------------------
# Dialogs
# -----------------------------------------------------------------------------
@st.dialog("Import Records")
def _show_import_records_dialog(account_id: str) -> None:
    with st.form("import_records_form", clear_on_submit=False):
        xlsx_file = st.file_uploader(
            "Import account records from file",
            type=["xlsx"],
            key="import_xlsx_uploader",
        )
        submitted = st.form_submit_button("Import", type="primary")
    if submitted:
        if xlsx_file is None:
            st.toast("Please upload an .xlsx file first", icon="⚠️")
        else:
            import_account_records(account_id, xlsx_file)
            st.cache_data.clear()
            st.rerun()


@st.dialog("Delete Account?")
def _show_delete_confirm_dialog(account_id: str, account_display_label: str) -> None:
    st.warning(
        f"Delete Account {account_display_label}? \n\n"
        "All transactions and account records will be permanently deleted.\n"
        "This action cannot be undone."
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel", key="delete_confirm_cancel"):
            st.session_state["show_delete_account_confirm"] = False
            st.rerun()
    with col2:
        if st.button("Delete", type="primary", key="delete_confirm_confirm"):
            if delete_account(account_id):
                st.session_state["show_delete_account_confirm"] = False
                st.cache_data.clear()  # clear cached loads (accounts, rates, symbols, etc.)
                st.rerun()
            # else: toast already shown by delete_account


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:

    st.subheader("Portfolio Options")

    st.toggle("Hide Balances", key="hide_balances_toggle")

    account_display_label = st.radio(
        "Select an account",
        account_display_labels,
        key="account_display_label",
    )
    # Update selected account state (derived, but tied to user selection)
    idx = account_display_labels.index(account_display_label)
    selected = accounts[idx]
    st.session_state["account_id"] = selected.id

    # --- Account operations row ---
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        create_clicked = st.button(
            "",
            icon=":material/add:",
            type="secondary",
            help="Create a new account",
            key="create_new_account_button",
        )

    with col2:
        import_clicked = st.button(
            "",
            icon=":material/upload_file:",
            type="secondary",
            help="Import records",
            key="import_records_button",
        )

    with col3:
        edit_clicked = st.button(
            "",
            icon=":material/edit:",
            type="secondary",
            help="Edit account",
            key="edit_account_button",
        )

    with col4:
        delete_clicked = st.button(
            "",
            icon=":material/delete:",
            type="secondary",
            help="Delete account",
            key="delete_account_button",
        )

    # --- Account operation logic ---
    if create_clicked:
        st.session_state["show_create_account_dialog"] = True
        st.rerun()

    if st.session_state.get("show_create_account_dialog", False):
        create_account_dialog(benchmark_symbols)
        st.session_state["show_create_account_dialog"] = False

    if import_clicked:
        st.session_state["show_import_records_dialog"] = True
        st.rerun()

    if st.session_state.get("show_import_records_dialog", False):
        _show_import_records_dialog(st.session_state["account_id"])
        st.session_state["show_import_records_dialog"] = False

    if edit_clicked:
        st.session_state["show_edit_account_dialog"] = True
        st.rerun()

    if st.session_state.get("show_edit_account_dialog", False):
        edit_account_dialog(
            st.session_state["account_id"],
            st.session_state["account_display_label"],
            benchmark_symbols,
        )
        st.session_state["show_edit_account_dialog"] = False

    if delete_clicked:
        st.session_state["show_delete_account_confirm"] = True
        st.rerun()

    if st.session_state.get("show_delete_account_confirm", False):
        _show_delete_confirm_dialog(
            account_id=st.session_state["account_id"],
            account_display_label=st.session_state["account_display_label"],
        )

    # Benchmark select: default to account benchmark if present
    account_benchmark = selected.benchmark
    if account_benchmark in benchmark_symbols:
        benchmark_idx = benchmark_symbols.index(account_benchmark)
    else:
        logger.warning(
            "Account benchmark %s not found in benchmarks list. Using default.",
            account_benchmark,
        )
        benchmark_idx = 0

    benchmark = st.selectbox(
        "Select a benchmark",
        benchmark_symbols,
        index=benchmark_idx if benchmark_symbols else 0,
    )
    st.session_state["benchmark"] = benchmark

    # Add transaction button
    if st.button(
        "Record Transaction",
        icon=":material/edit:",
        type="primary",
        key="record_transaction_button",
        width="stretch",
    ):
        st.session_state["show_transaction_form_dialog"] = True
        st.rerun()

    if st.session_state.get("show_transaction_form_dialog", False):
        transaction_form(
            account_id=st.session_state["account_id"],
            account_name=account_display_label,
            portfolio_symbols=st.session_state.get("portfolio_symbols"),
            holdings_qty=st.session_state.get("portfolio_holdings_qty"),
            fx_rate=st.session_state["rates"]["fx_rate"],
            portfolio_value=st.session_state.get("portfolio_value", 0.0),
            cash_balance=st.session_state.get("cash_balance", 0.0),
        )
        st.session_state["show_transaction_form_dialog"] = False

    st.divider()

    # --- Data refresh ---
    st.subheader("Data Refresh Options")

    if st.button(
        "Force Data Refresh",
        icon=":material/refresh:",
        type="primary",
        key="full_data_refresh_button",
        width="stretch",
    ):
        st.session_state["_last_missing_attempted"] = set(
            st.session_state["page_symbols"]
        )
        start_refresh_job(
            symbols=st.session_state["page_symbols"],
            blocking=True,
            force=True,
            active_page=st.session_state["active_page"],
            start_date=st.session_state["start_date"],
            end_date=st.session_state["end_date"],
        )

    if config.debug:
        st.divider()
        st.subheader("Debug Options")
        st.toggle("Show Session State", key="show_session_state_toggle")

    st.divider()
    if st.button(
        "Logout",
        icon=":material/logout:",
        type="secondary",
        key="logout_button",
        width="stretch",
    ):
        sb = _get_supabase_client()
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# -----------------------------------------------------------------------------
# Debug
# -----------------------------------------------------------------------------
if config.debug:
    st.warning("Developer mode", icon="⚠️")

if st.session_state.get("show_session_state_toggle", False):
    st.divider()
    st.subheader("Debug Data")
    st.write(st.session_state)

# -----------------------------------------------------------------------------
# Run Navigation (pages render after sidebar state is established)
# -----------------------------------------------------------------------------
pg.run()
