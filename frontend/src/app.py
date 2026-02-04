from datetime import datetime, timedelta
import logging

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.services.streamlit_data import (
    get_api_client,
    import_account_records,
    load_account_summary,
    load_available_securities_list,
    load_rates,
)
from src.shared.config_loader import load_accounts_config, load_symbols_config
from src.shared.env_loader import config
from src.shared.logging import setup_logging
from src.utils.jobs import start_refresh_job

setup_logging()
logger = logging.getLogger(__name__)

# --- Page config -------------------------------------------------------------
st.set_page_config(
    page_title="Portfolio Dashboard",
    layout="wide",
    page_icon=":bar_chart:",
    initial_sidebar_state="expanded",
)

st_autorefresh(interval=config.app_refresh_interval, key="app_autorefresh")

# --- Remove Streamlit header space ------------------------------------------
st.markdown(
    """
<style>
    /* Main container CSS */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1200px;
    }

    /* Small metrics CSS */

    /* Metric label */
    div[data-testid="stMetricLabel"] {
        font-size: 14px;
    }

    /* Main metric value */
    div[data-testid="stMetricValue"] {
        font-size: 16px;
        font-weight: bold;
    }

    /* Delta indicator */
    div[data-testid="stMetricDelta"] {
        font-size: 12px;
    }
</style>
""",
    unsafe_allow_html=True,
)


# --- Disclaimer ----------------------------------------------------------------
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

# --- Navigation --------------------------------------------------------------
pages = [
    st.Page(
        page="pages/1_Market.py",
        title="🏦 Market Watch",
        default=False,
    ),
    st.Page(
        page="pages/2_Portfolio.py",
        title="📊 Portfolio",
        default=True,
    ),
    st.Page(
        page="pages/9_About.py",
        title="ℹ️ About",
        default=False,
    ),
]
pg = st.navigation(pages)

# --- Services / config -------------------------------------------------------
api = get_api_client()

# --- Get accounts and account holdings ----------------------------------------------------------------
accounts = load_accounts_config().accounts
account_numbers = [account.number for account in accounts]
account_names = [f"{account.type} #{account.number}" for account in accounts]

# --- Session state bootstrap -------------------------------------------------
# Date range (1-year window, only set once)
if "start_date" not in st.session_state or "end_date" not in st.session_state:
    now = datetime.now()
    st.session_state["start_date"] = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    st.session_state["end_date"] = now.strftime("%Y-%m-%d")

# Default states for UI elements
st.session_state.setdefault("hide_balances_toggle", False)
st.session_state.setdefault("account_name", account_names[0])
st.session_state.setdefault("live_data_toggle", False)
st.session_state.setdefault("show_session_state_toggle", False)


# --- Symbol set construction -------------------------------------------------
# Header symbols
symbols_config = load_symbols_config()
header_symbols = symbols_config.snapshot.symbols
benchmark_symbols = symbols_config.benchmarks.symbols
st.session_state["header_symbols"] = header_symbols
st.session_state["benchmark_symbols"] = benchmark_symbols

# Market symbols
market_etf_symbols = sorted(
    [symbol for group in symbols_config.base_market_etfs for symbol in group.symbols]
)
st.session_state["market_etf_symbols"] = market_etf_symbols
market_stock_symbols = sorted(
    [symbol for group in symbols_config.base_market_stocks for symbol in group.symbols]
)
st.session_state["market_stock_symbols"] = market_stock_symbols

market_symbols = sorted(set(market_etf_symbols) | set(market_stock_symbols))
st.session_state["market_symbols"] = market_symbols

# API loaded session state data
available_symbols = load_available_securities_list()
st.session_state["available_symbols"] = available_symbols

rates = load_rates()
st.session_state["rates"] = rates

# --- Sidebar -----------------------------------------------------------------
with st.sidebar:
    if config.debug:
        st.warning("Developer mode active", icon="⚠️")

    st.subheader("Portfolio Options")

    hide_balances = st.toggle(
        "Hide Balances",
        key="hide_balances_toggle",
    )

    account_name = st.radio(
        "Select an account",
        account_names,
        key="account_name",
    )
    idx = account_names.index(account_name)
    st.session_state["account_number"] = accounts[idx].number
    st.session_state["account_status"] = accounts[idx].status
    st.session_state["account_owner"] = accounts[idx].owner
    st.session_state["account_type"] = accounts[idx].type

    account_benchmark = accounts[idx].benchmark
    if account_benchmark not in benchmark_symbols:
        st.toast(
            f"Account benchmark {account_benchmark} not found in benchmarks list. Using default benchmark instead.",
            icon="⚠️",
        )
        logger.warning(
            "Account benchmark %s not found in benchmarks list. Using default benchmark instead.",
            account_benchmark,
        )
        benchmark_idx = 0
    else:
        benchmark_idx = benchmark_symbols.index(account_benchmark)

    benchmark = st.selectbox(
        "Select a benchmark", benchmark_symbols, index=benchmark_idx
    )
    st.session_state["benchmark"] = benchmark

    with st.popover("Import account records"):
        xlsx_file = st.file_uploader(
            "Import account records",
            type=["xlsx"],
            key="import_xlsx_uploader",
        )
        import_xlsx = st.button(
            "Import File",
            icon=":material/upload_file:",
            type="secondary",
            key="import_xlsx_button",
        )
    if import_xlsx:
        if xlsx_file is None:
            st.toast("Please upload an .xlsx file first", icon="⚠️")
        else:
            import_account_records(st.session_state["account_number"], xlsx_file)

    st.divider()

    st.subheader("Data Refresh Options")

    full_data_refresh = st.button(
        "Refresh All Data",
        icon=":material/refresh:",
        type="primary",
        key="full_data_refresh_button",
    )
    if full_data_refresh:
        all_account_symbols = []
        for account_number in account_numbers:
            account_summary = load_account_summary(account_number)
            all_account_symbols.extend(account_summary["open_positions"])
        all_account_symbols = list(set(all_account_symbols))
        symbols_to_fetch = sorted(
            set(header_symbols)
            | set(benchmark_symbols)
            | set(market_symbols)
            | set(all_account_symbols)
        )
        start_refresh_job(symbols_to_fetch, blocking=False, intraday=False)
        st.toast("Background EOD refresh started", icon="🔄")

    if config.debug:
        st.divider()
        st.subheader("Debug Options")
        st.toggle(
            "Show Session State",
            key="show_session_state_toggle",
        )

# --- Run Navigation ----------------------------------------------------------
pg.run()

# --- Debug ------------------------------------------------------------------
if st.session_state["show_session_state_toggle"]:
    st.divider()
    st.subheader("Debug Data")
    st.write(st.session_state)
