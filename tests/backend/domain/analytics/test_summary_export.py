from datetime import date, datetime

import pytest

from src.backend.domain.analytics.allocation import CashSlice
from src.backend.domain.analytics.summary_export import build_summary_rows
from src.backend.domain.entities.account import AccountEntity, Category, Holding
from src.backend.domain.entities.fixed_income import FixedIncomeType
from src.backend.domain.entities.security import SecurityType


def _entity(number: str, name: str, type: str = "TFSA") -> AccountEntity:
    return AccountEntity(
        id=f"id-{number}",
        number=number,
        name=name,
        owner="user-1",
        type=type,
        currency="CAD",
        tax_status="Registered",
        benchmark="XIU.TO",
        last_modified=datetime(2025, 1, 1),
    )


def _holding(
    symbol: str,
    account: str,
    market_value: float,
    book_value: float,
    weight: float,
    **overrides,
) -> Holding:
    fields = dict(
        symbol=symbol,
        account=account,
        name=f"{symbol} Inc",
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        currency="USD",
        volume=0.0,
        change=0.0,
        change_percent=0.0,
        previous_close=1.0,
        holding_category=Category.EQUITY,
        security_type=SecurityType.STOCK,
        fx_rate=1.35,
        open_date=date(2025, 1, 2),
        open_qty=10,
        breakeven_price=1.0,
        book_value=book_value,
        market_value=market_value,
        gain=market_value - book_value,
        gain_pct=(market_value - book_value) / book_value,
        weight=weight,
        intraday_change=0.0,
        intraday_change_pct=0.0,
        distance_to_breakeven=0.0,
        fx_exposure=0.0,
        pnl_contribution=0.0,
        intraday_contribution=0.0,
        days_held=1,
    )
    fields.update(overrides)
    return Holding(**fields)


ACCOUNTS = [_entity("ACC-A", "Alice TFSA"), _entity("ACC-B", "Bob RRSP", type="RRSP")]


def test_rows_cover_every_asset_type_with_account_details():
    total = 10_000.0
    holdings = [
        _holding("MSFT", "ACC-B", 2_000.0, 1_500.0, 0.2),
        _holding(
            "XIU.TO",
            "ACC-A",
            1_000.0,
            900.0,
            0.1,
            security_type=SecurityType.ETF,
            currency="CAD",
        ),
        _holding(
            "AAPL",
            "ACC-A",
            500.0,
            400.0,
            0.05,
            holding_category=Category.CALL_OPTION,
            option_osi="AAPL270115C00150000",
            option_strike=150.0,
            option_expiry=date(2027, 1, 15),
            open_qty=1,
        ),
        _holding(
            "AAPL",
            "ACC-A",
            100.0,
            200.0,
            0.01,
            holding_category=Category.PUT_OPTION,
            option_osi="AAPL270115P00122500",
            option_strike=122.5,
            option_expiry=date(2027, 1, 15),
            open_qty=1,
        ),
        _holding(
            "GIC-5.00-20261107",
            "ACC-B",
            5_100.0,
            5_000.0,
            0.51,
            name="Example Bank 5.00% Nov 07 2026",
            holding_category=Category.FIXED_INCOME,
            security_type=SecurityType.GIC,
            fi_type=FixedIncomeType.GIC,
            currency="CAD",
        ),
        _holding(
            "TD-4.00-20270301",
            "ACC-B",
            800.0,
            800.0,
            0.08,
            name="Other Bank 4.00% Mar 01 2027",
            holding_category=Category.FIXED_INCOME,
            security_type=SecurityType.GIC,
            fi_type=FixedIncomeType.TERM_DEPOSIT,
            currency="CAD",
        ),
    ]
    cash = [CashSlice("ACC-A", "CAD", 700.0), CashSlice("ACC-B", "USD", -200.0)]

    rows = build_summary_rows(holdings, ACCOUNTS, cash, total)

    # Sorted by account, securities by symbol, cash last
    assert [(r.account_number, r.symbol) for r in rows] == [
        ("ACC-A", "AAPL270115C00150000"),
        ("ACC-A", "AAPL270115P00122500"),
        ("ACC-A", "XIU.TO"),
        ("ACC-A", "CASH"),
        ("ACC-B", "GIC-5.00-20261107"),
        ("ACC-B", "MSFT"),
        ("ACC-B", "TD-4.00-20270301"),
        ("ACC-B", "CASH"),
    ]
    assert [r.asset_type for r in rows] == [
        "Call Option",
        "Put Option",
        "ETF",
        "Cash",
        "GIC",
        "Stock",
        "Term Deposit",
        "Cash",
    ]
    assert {r.account_name for r in rows[:4]} == {"Alice TFSA"}
    assert {r.account_type for r in rows[4:]} == {"RRSP"}

    call, put, etf, cash_a, gic, stock, _td, cash_b = rows
    assert call.name == "AAPL Jan 15 2027 150 Call"
    assert put.name == "AAPL Jan 15 2027 122.5 Put"
    assert etf.name == "XIU.TO Inc"
    assert gic.name == "Example Bank 5.00% Nov 07 2026"
    assert (stock.book_value, stock.market_value, stock.gain) == (
        1_500.0,
        2_000.0,
        500.0,
    )
    assert stock.gain_pct == pytest.approx(500.0 / 1_500.0)
    assert stock.quantity == 10

    assert (cash_a.name, cash_a.currency) == ("Cash (CAD)", "CAD")
    assert cash_a.book_value == cash_a.market_value == 700.0
    assert (cash_a.gain, cash_a.gain_pct, cash_a.quantity) == (0.0, None, None)
    assert cash_a.weight == pytest.approx(0.07)
    # Margin shows as a negative cash row
    assert cash_b.market_value == -200.0
    assert cash_b.weight == pytest.approx(-0.02)

    assert sum(r.market_value for r in rows) == pytest.approx(total)
    assert sum(r.weight for r in rows) == pytest.approx(1.0)


def test_unknown_account_and_empty_portfolio():
    rows = build_summary_rows(
        [_holding("AAPL", "GONE", 100.0, 50.0, 1.0)], ACCOUNTS, [], 100.0
    )
    assert (rows[0].account_number, rows[0].account_name, rows[0].account_type) == (
        "GONE",
        "",
        "",
    )

    empty = build_summary_rows([], ACCOUNTS[:1], [CashSlice("ACC-A", "CAD", 0.0)], 0.0)
    assert [(r.symbol, r.weight) for r in empty] == [("CASH", 0.0)]
