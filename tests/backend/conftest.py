from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, cast

import pytest

from backend.domain.entities.account import (
    Category,
    Currency,
    OpenLot,
    Transaction,
    TransactionKind,
)
from backend.domain.entities.security import (
    Bar,
    GlobalRates,
    Profile,
    Quote,
    SecurityType,
)


def build_bars(
    symbol: str,
    closes: list[float],
    start: datetime = datetime(2025, 1, 1, 16, 0, 0),
) -> list[Bar]:
    """Deterministic OHLCV bars from a provided close sequence."""
    bars: list[Bar] = []
    for offset, close in enumerate(closes):
        bars.append(
            Bar(
                symbol=symbol,
                date=start + timedelta(days=offset),
                open=close - 1.0,
                high=close + 1.0,
                low=close - 2.0,
                close=close,
                volume=1_000_000 + (offset * 10_000),
            )
        )
    return bars


def build_quote(
    symbol: str = "AAPL",
    close: float = 110.0,
    timestamp: datetime = datetime(2025, 1, 10, 16, 0, 0),
) -> Quote:
    return Quote(
        symbol=symbol,
        name=f"{symbol} Inc",
        exchange="NASDAQ",
        open=close - 1.5,
        high=close + 1.5,
        low=close - 2.0,
        close=close,
        currency="USD",
        volume=2_500_000,
        change=1.25,
        change_percent=1.15,
        previousClose=close - 1.25,
        timestamp=timestamp,
    )


def build_profile(
    symbol: str = "AAPL",
    as_of: datetime = datetime(2025, 1, 10, 16, 0, 0),
) -> Profile:
    return Profile(
        symbol=symbol,
        name=f"{symbol} Inc",
        date=as_of,
        type=SecurityType.STOCK,
        exchange="NASDAQ",
        currency="USD",
        industry="Technology",
        sector="Information Technology",
        country="US",
    )


def build_global_rates(
    rf_rate: float = 4.5,
    fx_rate: float = 1.35,
    as_of: datetime = datetime(2025, 1, 10, 16, 0, 0),
) -> GlobalRates:
    return GlobalRates(date=as_of, rf_rate=rf_rate, fx_rate=fx_rate)


def build_security_inputs(
    symbol: str = "AAPL",
    closes: list[float] | None = None,
) -> dict[str, Quote | list[Bar] | Profile | GlobalRates]:
    closes = closes or [100.0, 101.0, 102.5, 103.0, 104.25, 106.0]
    return {
        "quote": build_quote(symbol=symbol, close=closes[-1]),
        "bars": build_bars(symbol=symbol, closes=closes),
        "profile": build_profile(symbol=symbol),
        "rates": build_global_rates(),
    }


def build_account_inputs(
    account_number: str = "ACC-001",
    owner: str = "Test Owner",
) -> dict[str, str | list[Transaction]]:
    tx_base_date = date(2025, 1, 2)
    transactions = [
        Transaction(
            transaction_date=tx_base_date,
            settlement_date=tx_base_date + timedelta(days=2),
            transaction_type=TransactionKind.BUY,
            symbol="AAPL",
            market="USA",
            description="AAPL common shares",
            quantity=10,
            currency=Currency.USD,
            price=100.0,
            commission=1.0,
            exchange_rate=1.35,
            fees_paid=0.0,
            amount=-1_351.0,
        ),
        Transaction(
            transaction_date=tx_base_date + timedelta(days=10),
            settlement_date=tx_base_date + timedelta(days=12),
            transaction_type=TransactionKind.SELL,
            symbol="AAPL",
            market="USA",
            description="AAPL partial sale",
            quantity=4,
            currency=Currency.USD,
            price=110.0,
            commission=1.0,
            exchange_rate=1.36,
            fees_paid=0.0,
            amount=597.4,
        ),
    ]
    return {
        "account_number": account_number,
        "account_name": owner,
        "transactions": transactions,
    }


def build_portfolio_inputs() -> dict[str, object]:
    return {
        "id": "PORT-001",
        "cash": 2_500.0,
        "positions": [
            OpenLot(
                symbol="AAPL",
                option_osi=None,
                category=Category.EQUITY,
                open_date=date(2025, 1, 2),
                option_expiry=None,
                option_strike=None,
                open_qty=6,
                acb_per_sh=135.10,
                book_value=810.6,
            )
        ],
        "rates": build_global_rates(rf_rate=4.5, fx_rate=1.35),
    }


@pytest.fixture
def security_bars() -> list[Bar]:
    """Default deterministic close-price sequence for security tests."""
    return build_bars(symbol="AAPL", closes=[100.0, 102.0, 101.5, 103.5, 105.0, 106.0])


@pytest.fixture
def quote_profile_rates() -> dict[str, Quote | Profile | GlobalRates]:
    """Bundle for quote/profile/rates test setup."""
    return {
        "quote": build_quote(symbol="AAPL", close=106.0),
        "profile": build_profile(symbol="AAPL"),
        "rates": build_global_rates(rf_rate=4.25, fx_rate=1.34),
    }


@pytest.fixture
def equity_transactions() -> list[Transaction]:
    """Simple equity buy/sell scenario."""
    return cast(list[Transaction], build_account_inputs()["transactions"])


@pytest.fixture
def option_transactions() -> list[Transaction]:
    """Call-option open/close scenario with deterministic P/L."""
    base = date(2025, 2, 3)
    return [
        Transaction(
            transaction_date=base,
            settlement_date=base + timedelta(days=1),
            transaction_type=TransactionKind.BUY,
            symbol="AAPL",
            market="USA",
            description="Call AAPL 03/21/25 200",
            quantity=1,
            currency=Currency.USD,
            price=2.5,
            commission=0.5,
            exchange_rate=1.34,
            fees_paid=0.0,
            amount=-335.5,
        ),
        Transaction(
            transaction_date=base + timedelta(days=14),
            settlement_date=base + timedelta(days=15),
            transaction_type=TransactionKind.SELL,
            symbol="AAPL",
            market="USA",
            description="Call AAPL 03/21/25 200",
            quantity=1,
            currency=Currency.USD,
            price=3.0,
            commission=0.5,
            exchange_rate=1.35,
            fees_paid=0.0,
            amount=404.5,
        ),
    ]


@pytest.fixture
def cashflow_transactions() -> list[Transaction]:
    """Cashflow-only scenario: contribution, dividend, and fee."""
    base = date(2025, 1, 5)
    return [
        Transaction(
            transaction_date=base,
            settlement_date=base,
            transaction_type=TransactionKind.CONTRIB,
            symbol="",
            market="CASH",
            description="Cash contribution",
            quantity=0,
            currency=Currency.CAD,
            price=0.0,
            commission=0.0,
            exchange_rate=1.0,
            fees_paid=0.0,
            amount=5_000.0,
        ),
        Transaction(
            transaction_date=base + timedelta(days=7),
            settlement_date=base + timedelta(days=7),
            transaction_type=TransactionKind.DIVIDEND,
            symbol="AAPL",
            market="USA",
            description="Quarterly dividend",
            quantity=0,
            currency=Currency.USD,
            price=0.0,
            commission=0.0,
            exchange_rate=1.35,
            fees_paid=0.0,
            amount=24.3,
        ),
        Transaction(
            transaction_date=base + timedelta(days=10),
            settlement_date=base + timedelta(days=10),
            transaction_type=TransactionKind.FEE,
            symbol="",
            market="CASH",
            description="Account fee",
            quantity=0,
            currency=Currency.CAD,
            price=0.0,
            commission=0.0,
            exchange_rate=1.0,
            fees_paid=0.0,
            amount=-12.0,
        ),
    ]


@pytest.fixture
def security_inputs_builder() -> Callable[..., dict[str, object]]:
    return build_security_inputs


@pytest.fixture
def account_inputs_builder() -> Callable[..., dict[str, object]]:
    return build_account_inputs


@pytest.fixture
def portfolio_inputs_builder() -> Callable[..., dict[str, object]]:
    return build_portfolio_inputs
