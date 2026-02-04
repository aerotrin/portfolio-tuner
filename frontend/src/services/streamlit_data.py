from dataclasses import dataclass, field
import logging
from typing import Any

import requests
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from src.services.api_client import APIClient
from src.shared.dto import TransactionCreate


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
@st.cache_resource
def get_api_client() -> APIClient:
    """One shared API client per Streamlit session."""
    return APIClient()


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
def load_account_summary(account: str, account_name: str | None = None) -> dict:
    """Load account symbols from API for given account."""
    api = get_api_client()
    try:
        return api.get_account_summary(account, account_name)
    except Exception:
        st.error(
            f"Failed to load account summary: {account_name}. Try reimporting the account records."
        )
        logger.exception("Failed to load account summary for %s", account_name)
        st.stop()


@st.cache_data(show_spinner="Loading account records…")
def load_account_records(account: str, account_name: str) -> AccountRecords:
    """Load transactions, closed lots, and cash flows for given account."""
    api = get_api_client()
    records = AccountRecords()

    try:
        records.transactions = list(api.get_account_transactions(account, account_name))
    except Exception:
        st.error(f"Failed to get transactions data: {account_name}")
        logger.exception("Failed to get transactions data for %s", account_name)

    try:
        records.closed_lots = list(api.get_account_closed_lots(account, account_name))
    except Exception:
        st.error(f"Failed to get closed lots data: {account_name}")
        logger.exception("Failed to get closed lots data for %s", account_name)

    try:
        records.cash_flows = list(api.get_account_cash_flows(account, account_name))
    except Exception:
        st.error(f"Failed to get cash flows data: {account_name}")
        logger.exception("Failed to get cash flows data for %s", account_name)

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
def load_portfolio_data_intraday(
    account: str,
    account_name: str,
) -> PortfolioData:
    """Load intraday portfolio summary + holdings snapshot."""
    api = get_api_client()
    portfolio = PortfolioData()

    try:
        portfolio.summary = api.get_portfolio_summary(account, account_name)
    except Exception:
        st.error(f"Failed to get portfolio summary data: {account_name}")
        logger.exception("Failed to get portfolio summary data for %s", account_name)
        st.stop()

    try:
        portfolio.holdings = api.get_portfolio_holdings(account, account_name)
    except Exception:
        st.error(f"Failed to get portfolio holdings data: {account_name}")
        logger.exception("Failed to get portfolio holdings data for %s", account_name)
        st.stop()

    return portfolio


@st.cache_data(show_spinner="Loading portfolio data…")
def load_portfolio_data_eod(
    account: str,
    account_name: str,
) -> PortfolioData:
    """Load EOD portfolio metrics + time-series indicators."""
    api = get_api_client()
    portfolio = PortfolioData()

    try:
        portfolio.metrics = api.get_portfolio_metrics(account, account_name)
    except Exception:
        st.error(f"Failed to get portfolio metrics data: {account_name}")
        logger.exception("Failed to get portfolio metrics data for %s", account_name)
        st.stop()

    try:
        indicators = list(api.get_portfolio_indicators(account, account_name))
        # Keep your existing downstream assumption that portfolio indicators live under "PORTF"
        portfolio.indicators["PORTF"] = indicators
    except Exception:
        st.error(f"Failed to get portfolio indicators data: {account_name}")
        logger.exception("Failed to get portfolio indicators data for %s", account_name)
        st.stop()

    try:
        correlation_matrix = api.get_portfolio_correlation_matrix(account, account_name)
        portfolio.correlation_matrix = correlation_matrix
    except Exception:
        st.error(f"Failed to get portfolio correlation matrix data: {account_name}")
        logger.exception(
            "Failed to get portfolio correlation matrix data for %s", account_name
        )
        st.stop()

    return portfolio


def create_transaction(account: str, transaction: TransactionCreate) -> None:
    """
    Create a transaction.
    Return a simple success message for the UI.
    """
    api = get_api_client()
    try:
        api.create_transaction(account, transaction)
        st.success("Transaction recorded.")
    except Exception:
        st.error("Failed to record transaction.")
        logger.exception("Failed to record transaction.")


def delete_transaction(account: str, transaction_id: str) -> None:
    """
    Delete a transaction.
    Return a simple success message for the UI.
    """
    api = get_api_client()
    try:
        api.delete_transaction(account, transaction_id)
        st.success("Transaction deleted.")
    except Exception:
        st.error("Failed to delete transaction.")
        logger.exception("Failed to delete transaction %s", transaction_id)


def import_account_records(account: str, file_data: UploadedFile) -> None:
    api = get_api_client()
    try:
        api.import_account(account, file_data)
        st.cache_data.clear()
        st.toast("Account imported from xlsx", icon="✅")
        logger.info("Account imported from xlsx for account %s", account)
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
            "Import from xlsx failed for account %s: %s",
            account,
            msg,
        )
