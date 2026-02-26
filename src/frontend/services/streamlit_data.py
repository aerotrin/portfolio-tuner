from dataclasses import dataclass, field
import logging
from typing import Any

import requests
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from frontend.services.api_client import APIClient
from frontend.shared.dto import (
    AccountCreateRequest,
    AccountEntity,
    AccountPatchRequest,
    TransactionCreate,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers (Streamlit-friendly shapes)
# ---------------------------------------------------------------------------
@dataclass
class SecurityData:
    quote: dict[str, dict[str, Any]] = field(default_factory=dict)
    profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    bars: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    indicators: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass
class PortfolioData:
    summary: dict[str, Any] = field(default_factory=dict)
    holdings: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    indicators: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    correlation_matrix: dict[str, dict[str, Any]] = field(default_factory=dict)
    securities: SecurityData = field(default_factory=SecurityData)


@dataclass
class AccountRecords:
    transactions: list[dict[str, Any]] = field(default_factory=list)
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    closed_lots: list[dict[str, Any]] = field(default_factory=list)
    cash_flows: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API caller / caching wrappers
# Any HTTP error should raise via requests.raise_for_status() inside APIClient.
# ---------------------------------------------------------------------------
def get_api_client() -> APIClient:
    """One API client per Streamlit user session, carrying the user's JWT."""
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = APIClient()
    client: APIClient = st.session_state["api_client"]
    token = st.session_state.get("jwt_token")
    if token:
        client.update_token(token)  # ensure client always has the latest token
    return client


@st.cache_data(show_spinner=False)
def load_rates() -> dict:
    """Load current exchange rates for CAD/USD and T-Bill 6m."""
    api = get_api_client()
    try:
        return api.get_rates()
    except Exception:
        st.error("Failed to get rates data.")
        logger.exception("Failed to get rates data.")
        st.stop()


@st.cache_data(show_spinner=False)
def load_accounts_list(user_id: str) -> list[AccountEntity]:  # noqa: ARG001
    """Load accounts from API (GET /accounts)."""
    api = get_api_client()
    try:
        raw = api.get_accounts()
    except Exception:
        st.error("Failed to load accounts from API. Ensure backend is running.")
        logger.exception("Failed to load accounts from API.")
        st.stop()
    return [AccountEntity.model_validate(a) for a in raw]


@st.cache_data(show_spinner=False)
def load_account_details(account_id: str) -> AccountEntity:
    """Load account from API (GET /accounts/{account_id})."""
    api = get_api_client()
    try:
        raw = api.get_account_details(account_id)
    except Exception:
        st.error("Failed to load account from API.")
        logger.exception("Failed to load account from API.")
        st.stop()
    return AccountEntity.model_validate(raw)


@st.cache_data(show_spinner=False)
def load_available_securities_list() -> list[str]:
    """Load list of available securities from API."""
    api = get_api_client()
    try:
        symbols = api.get_available_symbols()
    except Exception:
        st.error("Failed to get available securities list.")
        logger.exception("Failed to get available securities list.")
        st.stop()
    return symbols


def check_missing_symbols(symbols: tuple[str, ...]) -> list[str]:
    """Returns symbols not yet available (missing quotes or bars sync state)."""
    api = get_api_client()
    try:
        return api.check_symbols_availability(list(symbols))
    except Exception:
        logger.exception("Failed to check symbol availability")
        return []


@st.cache_data(show_spinner="Loading account records…")
def load_account_records(account_id: str) -> AccountRecords:
    """Load transactions, closed lots, and cash flows for given account id in a single request."""
    api = get_api_client()
    records = AccountRecords()
    try:
        batch = api.get_account_records(account_id)
        records.transactions = batch.get("transactions", [])
        records.open_positions = batch.get("open_positions", [])
        records.closed_lots = batch.get("closed_lots", [])
        records.cash_flows = batch.get("cash_flows", [])
    except Exception:
        st.error("Failed to get account records.")
        logger.exception("Failed to get account records for %s", account_id)
    return records


@st.cache_data(show_spinner="Loading securities data…")
def load_security_data(
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> SecurityData:
    """Load quote, profile, bars, metrics and indicators for given symbols in a single request."""
    api = get_api_client()
    data = SecurityData()

    if not symbols:
        return data

    try:
        batch = api.get_security_batch_analytics(symbols, start_date, end_date)
        if isinstance(batch, dict):
            for sym, analytics in batch.items():
                data.quote[sym] = analytics.get("quote") or {}
                data.profile[sym] = analytics.get("profile") or {}
                data.metrics[sym] = analytics.get("metrics") or {}
                data.bars[sym] = analytics.get("bars") or []
                data.indicators[sym] = analytics.get("indicators") or []
    except Exception:
        st.error("Failed to load securities data")
        logger.exception("Failed to load securities data for %s", symbols)

    return data


def load_single_security_quote(symbol: str) -> dict | None:
    api = get_api_client()
    try:
        return api.get_security_quote(symbol)
    except Exception:
        st.error(f"Failed to get quote data: {symbol}")
        logger.exception("Failed to get quote data for %s", symbol)
        return None


@st.cache_data(show_spinner="Loading portfolio data…")
def load_portfolio_snapshot(
    account_id: str,
    start_date: str | None,
    end_date: str | None,
) -> PortfolioData:
    """Load full portfolio snapshot with per-security analytics in a single request."""
    api = get_api_client()
    portfolio = PortfolioData()
    try:
        snap = api.get_portfolio(account_id, start_date, end_date)
        portfolio.summary = snap.get("summary", {})
        portfolio.holdings = snap.get("holdings", {})
        portfolio.metrics = snap.get("metrics", {})
        portfolio.indicators["PORTF"] = snap.get("indicators", [])
        portfolio.correlation_matrix = snap.get("correlation_matrix", {})
        for sym, analytics in snap.get("securities", {}).items():
            portfolio.securities.quote[sym] = analytics.get("quote") or {}
            portfolio.securities.profile[sym] = analytics.get("profile") or {}
            portfolio.securities.metrics[sym] = analytics.get("metrics") or {}
            portfolio.securities.bars[sym] = analytics.get("bars") or []
            portfolio.securities.indicators[sym] = analytics.get("indicators") or []
    except Exception:
        st.error("Failed to load portfolio data.")
        logger.exception("Failed to load portfolio snapshot for %s", account_id)
        st.stop()
    return portfolio


def create_transaction(account_id: str, transaction: TransactionCreate) -> None:
    """
    Create a transaction.
    Return a simple success message for the UI.
    """
    api = get_api_client()
    try:
        api.create_transaction(account_id, transaction)
        st.success("Transaction recorded.")
    except Exception:
        st.error("Failed to record transaction.")
        logger.exception("Failed to record transaction.")


def delete_transaction(account_id: str, transaction_id: str) -> str | None:
    """
    Delete a transaction. Returns None on success, or an error message string on failure.
    """
    api = get_api_client()
    try:
        api.delete_transaction(account_id, transaction_id)
        st.success("Transaction deleted.")
        return None
    except Exception:
        st.error("Failed to delete transaction.")
        logger.exception("Failed to delete transaction %s", transaction_id)
        return "Failed to delete transaction."


def import_account_records(account_id: str, file_data: UploadedFile) -> None:
    api = get_api_client()
    try:
        api.import_account(account_id, file_data)
        st.cache_data.clear()
        st.toast("Account imported from xlsx", icon="✅")
        logger.info("Account imported from xlsx for account_id %s", account_id)
    except requests.HTTPError as e:
        msg = "Import failed"
        if e.response is not None:
            try:
                detail = e.response.json().get("detail", "")
                if detail:
                    msg = str(detail)
            except Exception:
                pass
        st.toast(msg, icon="❌")
        logger.exception(
            "Import from xlsx failed for account_id %s: %s",
            account_id,
            msg,
        )


def create_account(payload: AccountCreateRequest) -> bool:
    """
    Create an account. Returns True on success, False on HTTP/other error.
    Shows a toast with the API detail on failure.
    """
    api = get_api_client()
    try:
        api.create_account(payload)
        return True
    except requests.HTTPError as e:
        msg = "Create account failed"
        if e.response is not None:
            try:
                detail = e.response.json().get("detail", "")
                if detail:
                    msg = str(detail)
            except Exception:
                pass
        st.toast(msg, icon="❌")
        logger.exception("Create account failed: %s", msg)
        return False
    except Exception:
        st.toast("Create account failed.", icon="❌")
        logger.exception("Create account failed")
        return False


def get_account_details(account_id: str) -> AccountEntity | None:
    """
    Get account details by ID. Returns AccountEntity on success, None on HTTP error.
    Shows a toast with the API detail on failure.
    """
    api = get_api_client()
    try:
        raw = api.get_account_details(account_id)
        return AccountEntity.model_validate(raw)
    except requests.HTTPError as e:
        msg = "Get account details failed"
        if e.response is not None:
            try:
                detail = e.response.json().get("detail", "")
                if detail:
                    msg = str(detail)
            except Exception:
                pass
        st.toast(msg, icon="❌")
        logger.exception("Get account details failed for %s: %s", account_id, msg)
        return None
    except Exception:
        st.toast("Get account details failed.", icon="❌")
        logger.exception("Get account details failed for %s", account_id)
        return None


def delete_account(account_id: str) -> bool:
    """
    Delete an account by ID. Returns True on success, False on HTTP error.
    Shows a toast with the API detail on failure.
    """
    api = get_api_client()
    try:
        api.delete_account(account_id)
        return True
    except requests.HTTPError as e:
        msg = "Delete account failed"
        if e.response is not None:
            try:
                detail = e.response.json().get("detail", "")
                if detail:
                    msg = str(detail)
            except Exception:
                pass
        st.toast(msg, icon="❌")
        logger.exception("Delete account failed for %s: %s", account_id, msg)
        return False
    except Exception:
        st.toast("Delete account failed.", icon="❌")
        logger.exception("Delete account failed for %s", account_id)
        return False


def patch_account(account_id: str, payload: AccountPatchRequest) -> bool:
    """
    Patch an account by ID. Returns True on success, False on HTTP error.
    Shows a toast with the API detail on failure.
    """
    api = get_api_client()
    try:
        api.patch_account(account_id, payload)
        return True
    except requests.HTTPError as e:
        msg = "Patch account failed"
        if e.response is not None:
            try:
                detail = e.response.json().get("detail", "")
                if detail:
                    msg = str(detail)
            except Exception:
                pass
        st.toast(msg, icon="❌")
        logger.exception("Patch account failed for %s: %s", account_id, msg)
        return False
    except Exception:
        st.toast("Patch account failed.", icon="❌")
        logger.exception("Patch account failed for %s", account_id)
        return False
