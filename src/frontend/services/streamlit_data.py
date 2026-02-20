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
class SecurityIntradayData:
    quote: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class SecurityEODData:
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


@dataclass
class AccountRecords:
    transactions: list[dict[str, Any]] = field(default_factory=list)
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
def load_accounts_list() -> list[AccountEntity]:
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
def load_available_securities_list() -> list[str]:
    """Load list of available securities from API."""
    api = get_api_client()
    try:
        return api.get_available_symbols()
    except Exception:
        st.error("Failed to get available securities list.")
        logger.exception("Failed to get available securities list.")
        st.stop()


@st.cache_data(show_spinner=False)
def load_account_summary(account_id: str) -> dict:
    """Load account summary from API for given account id."""
    api = get_api_client()
    try:
        return api.get_account_summary(account_id)
    except Exception:
        st.error("Failed to load account summary. Try reimporting the account records.")
        logger.exception("Failed to load account summary for %s", account_id)
        st.stop()


@st.cache_data(show_spinner="Loading account records…")
def load_account_records(account_id: str) -> AccountRecords:
    """Load transactions, closed lots, and cash flows for given account id."""
    api = get_api_client()
    records = AccountRecords()

    try:
        records.transactions = list(api.get_account_transactions(account_id))
    except Exception:
        st.error("Failed to get transactions data.")
        logger.exception("Failed to get transactions data for %s", account_id)

    try:
        records.closed_lots = list(api.get_account_closed_lots(account_id))
    except Exception:
        st.error("Failed to get closed lots data.")
        logger.exception("Failed to get closed lots data for %s", account_id)

    try:
        records.cash_flows = list(api.get_account_cash_flows(account_id))
    except Exception:
        st.error("Failed to get cash flows data.")
        logger.exception("Failed to get cash flows data for %s", account_id)

    return records


@st.cache_data(show_spinner=False)
def load_security_data_intraday(symbols: list[str]) -> SecurityIntradayData:
    """Load intraday/quote data for given symbols."""
    api = get_api_client()
    securities = SecurityIntradayData()

    if not symbols:
        return securities

    try:
        quotes = api.get_security_batch_quotes(symbols)
        for quote in quotes:
            sym = quote.get("symbol")
            if sym:
                securities.quote[sym] = quote
    except Exception:
        st.error(f"Failed to get quotes data: {symbols}")
        logger.exception("Failed to get quotes data for %s", symbols)

    return securities


@st.cache_data(show_spinner="Loading securities data…")
def load_security_data_eod(
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> SecurityEODData:
    """Load EOD bars/metrics/indicators for given symbols and date range."""
    api = get_api_client()
    securities = SecurityEODData()

    if not symbols:
        return securities

    # Profiles
    try:
        profiles = api.get_security_batch_profiles(symbols)
        for profile in profiles:
            sym = profile.get("symbol")
            if sym:
                securities.profile[sym] = profile
    except Exception:
        st.error(f"Failed to get profiles data: {symbols}")
        logger.exception("Failed to get profiles data for %s", symbols)

    # Bars (batch returns dict[symbol, list[Bar]])
    try:
        batch_bars = api.get_security_batch_bars(symbols, start_date, end_date)
        if isinstance(batch_bars, dict):
            for sym, bars in batch_bars.items():
                securities.bars[sym] = bars
    except Exception:
        st.error("Failed to get bars data.")
        logger.exception("Failed to get bars data for %s", symbols)

    # Metrics
    try:
        metrics = api.get_security_batch_metrics(symbols)
        for metric in metrics:
            sym = metric.get("symbol")
            if sym:
                securities.metrics[sym] = metric
    except Exception:
        st.error(f"Failed to get metrics data: {symbols}")
        logger.exception("Failed to get metrics data for %s", symbols)

    # Indicators (batch returns dict[symbol, list[indicator]])
    try:
        batch_indicators = api.get_security_batch_indicators(symbols)
        if isinstance(batch_indicators, dict):
            for sym, indicator in batch_indicators.items():
                securities.indicators[sym] = indicator
    except Exception:
        st.error(f"Failed to get indicators data: {symbols}")
        logger.exception("Failed to get indicators data for %s", symbols)

    return securities


def load_single_security_quote(symbol: str) -> dict | None:
    api = get_api_client()
    try:
        return api.get_security_quote(symbol)
    except Exception:
        st.error(f"Failed to get quote data: {symbol}")
        logger.exception("Failed to get quote data for %s", symbol)
        return None


@st.cache_data(show_spinner=False)
def load_portfolio_data_intraday(account_id: str) -> PortfolioData:
    """Load intraday portfolio summary + holdings snapshot."""
    api = get_api_client()
    portfolio = PortfolioData()

    try:
        portfolio.summary = api.get_portfolio_summary(account_id)
    except Exception:
        st.error("Failed to get portfolio summary data.")
        logger.exception("Failed to get portfolio summary data for %s", account_id)
        st.stop()

    try:
        portfolio.holdings = api.get_portfolio_holdings(account_id)
    except Exception:
        st.error("Failed to get portfolio holdings data.")
        logger.exception("Failed to get portfolio holdings data for %s", account_id)
        st.stop()

    return portfolio


@st.cache_data(show_spinner="Loading portfolio data…")
def load_portfolio_data_eod(account_id: str) -> PortfolioData:
    """Load EOD portfolio metrics + time-series indicators."""
    api = get_api_client()
    portfolio = PortfolioData()

    try:
        portfolio.metrics = api.get_portfolio_metrics(account_id)
    except Exception:
        st.error("Failed to get portfolio metrics data.")
        logger.exception("Failed to get portfolio metrics data for %s", account_id)
        st.stop()

    try:
        indicators = list(api.get_portfolio_indicators(account_id))
        # Keep your existing downstream assumption that portfolio indicators live under "PORTF"
        portfolio.indicators["PORTF"] = indicators
    except Exception:
        st.error("Failed to get portfolio indicators data.")
        logger.exception("Failed to get portfolio indicators data for %s", account_id)
        st.stop()

    try:
        correlation_matrix = api.get_portfolio_correlation_matrix(account_id)
        portfolio.correlation_matrix = correlation_matrix
    except Exception:
        st.error("Failed to get portfolio correlation matrix data.")
        logger.exception(
            "Failed to get portfolio correlation matrix data for %s", account_id
        )
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
