from datetime import date

import pandas as pd
import pytest


from src.backend.domain.analytics.account import _prep_transactions, run_records_parser
from src.backend.domain.entities.account import Category

BASE_COLUMNS = {
    "transaction_date": pd.Timestamp("2024-01-01"),
    "settlement_date": pd.Timestamp("2024-01-03"),
    "transaction_type": "Buy",
    "symbol": "AAPL",
    "market": "US",
    "description": "Common shares",
    "quantity": 0,
    "currency": "USD",
    "price": 0.0,
    "amount": 0.0,
}


def _tx(**overrides):
    row = BASE_COLUMNS.copy()
    row.update(overrides)
    return row


def test_prep_transactions_symbol_category_and_option_fields():
    tx = pd.DataFrame(
        [
            _tx(
                symbol="BNS.T",
                market="US",
                transaction_type="Buy",
                description="Common equity",
                quantity=1,
                amount=-10,
            ),
            _tx(
                symbol="RY",
                market="CDN",
                transaction_type="Buy",
                description="Common equity",
                quantity=1,
                amount=-10,
            ),
            _tx(
                transaction_type="Dividend",
                description="Quarterly distribution",
                quantity=0,
                amount=1.5,
            ),
            _tx(
                transaction_type="Fee",
                description="Trading fee",
                quantity=0,
                amount=-2,
            ),
            _tx(
                symbol="SPY",
                transaction_type="Buy",
                description="Call SPY 12/20/24 450",
                quantity=1,
                amount=-250,
            ),
            _tx(
                symbol="QQQ",
                transaction_type="Buy",
                description="Put QQQ 11/15/24 410.5",
                quantity=1,
                amount=-300,
            ),
            _tx(
                transaction_date=pd.Timestamp("2024-01-02"),
                symbol="XYZ",
                transaction_type="Return of Capital",
                description="Return of capital distribution",
                quantity=0,
                amount=15.0,
            ),
        ]
    )

    prepped = _prep_transactions(tx)

    assert prepped["symbol"].tolist()[:2] == ["BNS-T", "RY.TO"]
    assert prepped["category"].tolist()[2:4] == [Category.INCOME, Category.EXPENSE]

    call_row = prepped.loc[prepped["description"] == "Call SPY 12/20/24 450"].iloc[0]
    assert call_row["category"] == Category.CALL_OPTION
    assert call_row["option_expiry"] == date(2024, 12, 20)
    assert call_row["option_strike"] == 450.0
    assert call_row["option_osi"] == "SPY241220C00450000"

    put_row = prepped.loc[prepped["description"] == "Put QQQ 11/15/24 410.5"].iloc[0]
    assert put_row["category"] == Category.PUT_OPTION
    assert put_row["option_expiry"] == date(2024, 11, 15)
    assert put_row["option_strike"] == 410.5
    assert put_row["option_osi"] == "QQQ241115P00410500"

    roc_row = prepped.loc[prepped["transaction_type"] == "Return of Capital"].iloc[0]
    assert roc_row["category"] == Category.RETURN_OF_CAPITAL
    assert roc_row["qty_effect"] == 0


def test_run_records_parser_partial_full_close_and_oversell_clamp():
    tx = pd.DataFrame(
        [
            _tx(
                transaction_date=pd.Timestamp("2024-01-02"),
                settlement_date=pd.Timestamp("2024-01-04"),
                transaction_type="Buy",
                symbol="MSFT",
                quantity=100,
                price=10.0,
                amount=-1000.0,
            ),
            _tx(
                transaction_date=pd.Timestamp("2024-01-10"),
                settlement_date=pd.Timestamp("2024-01-12"),
                transaction_type="Sell",
                symbol="MSFT",
                quantity=40,
                price=12.0,
                amount=480.0,
            ),
            _tx(
                transaction_date=pd.Timestamp("2024-01-11"),
                settlement_date=pd.Timestamp("2024-01-13"),
                transaction_type="Sell",
                symbol="MSFT",
                quantity=1000,
                price=15.0,
                amount=900.0,
            ),
            _tx(
                transaction_date=pd.Timestamp("2024-02-01"),
                settlement_date=pd.Timestamp("2024-02-05"),
                transaction_type="Buy",
                symbol="MSFT",
                quantity=20,
                price=20.0,
                amount=-400.0,
            ),
        ]
    )

    open_lots, closed_lots, cash_flows = run_records_parser(tx)

    assert len(open_lots) == 1
    assert len(closed_lots) == 2
    assert len(cash_flows) == 0

    first_close, second_close = closed_lots
    assert first_close.close_qty == 40
    assert first_close.cost_basis == pytest.approx(400.0)
    assert first_close.gain == pytest.approx(80.0)

    # Oversell gets clamped to remaining quantity (60)
    assert second_close.close_qty == 60
    assert second_close.cost_basis == pytest.approx(600.0)
    assert second_close.gain == pytest.approx(300.0)

    # Full close reset means the next buy opens a fresh lot at the new date/cost basis
    assert open_lots[0].open_qty == 20
    assert open_lots[0].open_date == date(2024, 2, 1)
    assert open_lots[0].acb_per_sh == pytest.approx(20.0)
    assert open_lots[0].book_value == pytest.approx(400.0)


def test_run_records_parser_expired_option_uses_option_expiry_as_close_date():
    tx = pd.DataFrame(
        [
            _tx(
                transaction_date=pd.Timestamp("2024-01-05"),
                settlement_date=pd.Timestamp("2024-01-08"),
                transaction_type="Buy",
                symbol="SPY",
                description="Call SPY 03/15/24 500",
                quantity=1,
                price=2.5,
                amount=-250.0,
            ),
            _tx(
                transaction_date=pd.Timestamp("2024-03-16"),
                settlement_date=pd.Timestamp("2024-03-19"),
                transaction_type="Expired",
                symbol="SPY",
                description="Call SPY 03/15/24 500 expired",
                quantity=1,
                price=0.0,
                amount=0.0,
            ),
        ]
    )

    open_lots, closed_lots, cash_flows = run_records_parser(tx)

    assert len(open_lots) == 0
    assert len(closed_lots) == 1
    assert len(cash_flows) == 0

    closed = closed_lots[0]
    assert closed.is_expired is True
    assert closed.option_expiry == date(2024, 3, 15)
    assert closed.close_date == date(2024, 3, 15)
    assert closed.proceeds == pytest.approx(0.0)
    assert closed.cost_basis == pytest.approx(250.0)
    assert closed.gain == pytest.approx(-250.0)


def test_run_records_parser_cashflow_mapping_settlement_and_none_normalization():
    tx = pd.DataFrame(
        [
            _tx(
                transaction_type="Contrib",
                description="Cash contribution",
                quantity=0,
                amount=1000.0,
                currency="CAD",
                settlement_date=pd.Timestamp("2024-01-04"),
            ),
            _tx(
                transaction_type="Dividend",
                description="Dividend income",
                quantity=0,
                amount=25.0,
                settlement_date="None",
            ),
            _tx(
                transaction_type="Fee",
                description="Monthly fee",
                quantity=0,
                amount=-3.0,
                settlement_date=pd.NaT,
            ),
            _tx(
                transaction_date=pd.Timestamp("2024-01-02"),
                transaction_type="Return of Capital",
                symbol="XYZ",
                description="Return of capital distribution",
                quantity=0,
                amount=15.0,
                settlement_date=pd.Timestamp("2024-01-04"),
            ),
        ]
    )

    open_lots, closed_lots, cash_flows = run_records_parser(tx)

    assert len(open_lots) == 0
    assert len(closed_lots) == 0
    assert len(cash_flows) == 4

    contrib, dividend, fee, roc = cash_flows
    assert contrib.category == Category.CASH
    assert contrib.settlement_date == date(2024, 1, 4)

    assert dividend.category == Category.INCOME
    assert dividend.settlement_date is None

    assert fee.category == Category.EXPENSE
    assert fee.settlement_date is None

    assert roc.category == Category.RETURN_OF_CAPITAL
    assert roc.transaction_type == "Return of Capital"
    assert roc.amount == pytest.approx(15.0)


GIC_BUY = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon         5.00  FLEXIBLE GIC               AM NON-TRANSFERABLE DUE "
    "11/07/2024 05.000% SECURITIES OF A RELATED ISSUER UNSOLICITED"
)
GIC_INTEREST = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon 5.0000  Maturity NOV 07 2024 Coupon 5.0000 FLEXIBLE GIC               "
    "AM DUE 11/07/2024  INT  5.000% CPN INT   ON   20000 BND REC 11/06/24 PAY "
    "11/07/24"
)
GIC_REDEEMED = (
    "CIBC FLEXIBLE GIC               AM NON-TRANSFERABLE Maturity NOV 07 2024 "
    "Coupon 5.0000  FLEXIBLE GIC               AM DUE 11/07/2024  INT  5.000% "
    "ISSUE REDEEMED FOR CASH"
)


def _gic_rows(symbol: str = "") -> list[dict]:
    """One GIC's ledger lifecycle; the bank leaves the symbol blank."""
    common = dict(symbol=symbol, market="", currency="CAD")
    return [
        _tx(
            transaction_date=pd.Timestamp("2023-11-06"),
            settlement_date=pd.Timestamp("2023-11-07"),
            transaction_type="Buy",
            description=GIC_BUY,
            quantity=20000,
            price=100.0,
            amount=-20000.0,
            **common,
        ),
        _tx(
            transaction_date=pd.Timestamp("2024-11-07"),
            settlement_date=pd.Timestamp("2024-11-07"),
            transaction_type="Interest",
            description=GIC_INTEREST,
            quantity=0,
            amount=1000.0,
            **common,
        ),
        _tx(
            transaction_date=pd.Timestamp("2024-11-07"),
            settlement_date=pd.Timestamp("2024-11-07"),
            transaction_type="Redeemed",
            description=GIC_REDEEMED,
            quantity=20000,
            amount=20000.0,
            **common,
        ),
    ]


def test_open_ledger_gic_with_blank_symbol_gets_a_key_and_terms():
    open_lots, closed_lots, _ = run_records_parser(pd.DataFrame(_gic_rows()[:1]))

    assert closed_lots == []
    (lot,) = open_lots
    assert lot.symbol == "GIC-5.00-20241107"
    assert lot.category == Category.FIXED_INCOME
    assert lot.book_value == pytest.approx(20000.0)
    assert lot.principal == pytest.approx(20000.0)
    assert lot.interest_received == 0.0
    assert lot.terms is not None
    assert lot.terms.issue_date == date(2023, 11, 7)
    assert lot.terms.maturity_date == date(2024, 11, 7)
    assert lot.terms.annual_rate == pytest.approx(0.05)
    assert lot.terms.name == "CIBC FLEXIBLE GIC"


@pytest.mark.parametrize("symbol", ["", "GIC"])
def test_ledger_gic_lifecycle_closes_at_par_with_interest_attributed(symbol):
    open_lots, closed_lots, cash_flows = run_records_parser(
        pd.DataFrame(_gic_rows(symbol))
    )

    assert open_lots == []
    (closed,) = closed_lots
    assert closed.symbol == "GIC-5.00-20241107"
    assert closed.category == Category.FIXED_INCOME
    assert closed.cost_basis == pytest.approx(20000.0)
    assert closed.gain == pytest.approx(0.0)

    (interest,) = cash_flows
    assert interest.category == Category.INCOME
    assert interest.symbol == "GIC-5.00-20241107"
    assert interest.amount == pytest.approx(1000.0)


def test_two_gics_with_blank_symbols_stay_separate():
    other = GIC_BUY.replace("NOV 07 2024", "MAR 15 2026").replace("5.00 ", "3.25 ")
    rows = _gic_rows()[:1] + [
        _tx(
            transaction_date=pd.Timestamp("2025-03-14"),
            settlement_date=pd.Timestamp("2025-03-15"),
            transaction_type="Buy",
            symbol="",
            market="",
            currency="CAD",
            description=other,
            quantity=5000,
            price=100.0,
            amount=-5000.0,
        )
    ]

    open_lots, _, _ = run_records_parser(pd.DataFrame(rows))

    assert {lot.symbol: lot.book_value for lot in open_lots} == {
        "GIC-5.00-20241107": 20000.0,
        "GIC-3.25-20260315": 5000.0,
    }


def test_interest_received_reduces_what_the_open_lot_still_has_to_pay():
    rows = _gic_rows()[:2]

    (lot,) = run_records_parser(pd.DataFrame(rows))[0]

    assert lot.interest_received == pytest.approx(1000.0)


def test_manual_instrument_uses_its_stored_symbol_and_terms():
    key = "GIC-2.45-20261209-7f3a"
    terms = {
        "type": "GIC",
        "name": "Example Bank",
        "issue_date": date(2025, 12, 9),
        "maturity_date": date(2026, 12, 9),
        "annual_rate": 0.0245,
        "payment_frequency": "At Maturity",
        "compounding": "Simple",
        "redeemable": False,
    }
    rows = [
        _tx(
            transaction_date=pd.Timestamp("2025-12-09"),
            settlement_date=pd.Timestamp("2025-12-11"),
            transaction_type="Buy",
            symbol=key,
            market="CDN",
            currency="CAD",
            description="EXAMPLE BANK GIC",
            quantity=26104,
            price=100.0,
            amount=-26104.02,
            instrument_terms=terms,
        ),
        _tx(
            transaction_date=pd.Timestamp("2026-06-09"),
            settlement_date=pd.Timestamp("2026-06-09"),
            transaction_type="Interest",
            symbol=key,
            market="CDN",
            currency="CAD",
            description="EXAMPLE BANK GIC INTEREST",
            amount=100.0,
            instrument_terms=None,
        ),
    ]

    open_lots, _, cash_flows = run_records_parser(pd.DataFrame(rows))

    (lot,) = open_lots
    # The key is used as stored: no '.TO' suffix or dot rewriting
    assert lot.symbol == key
    assert lot.category == Category.FIXED_INCOME
    assert lot.principal == pytest.approx(26104.02)
    assert lot.terms.issue_date == date(2025, 12, 9)
    assert lot.interest_received == pytest.approx(100.0)
    assert cash_flows[0].symbol == key


def test_unparsed_fixed_income_row_falls_back_to_a_shared_key():
    rows = [
        _tx(
            transaction_type="Buy",
            symbol="",
            market="",
            currency="CAD",
            description="SOME ISSUER NOTE COUPON 4.1 DUE 2027",
            quantity=1000,
            amount=-1000.0,
        )
    ]

    (lot,) = run_records_parser(pd.DataFrame(rows))[0]

    assert lot.symbol == "FIXED-INCOME"
    assert lot.category == Category.FIXED_INCOME
    assert lot.terms is None


def test_closing_row_without_an_open_position_is_skipped():
    tx = pd.DataFrame([_gic_rows()[2]])

    open_lots, closed_lots, _ = run_records_parser(tx)

    assert open_lots == []
    assert closed_lots == []


def test_same_day_open_and_close_reports_zero_days_held():
    day = pd.Timestamp("2024-05-01")
    tx = pd.DataFrame(
        [
            _tx(
                transaction_date=day,
                transaction_type="Buy",
                symbol="MSFT",
                quantity=10,
                amount=-1000.0,
            ),
            _tx(
                transaction_date=day,
                transaction_type="Sell",
                symbol="MSFT",
                quantity=10,
                amount=1100.0,
            ),
        ]
    )

    _, closed_lots, _ = run_records_parser(tx)

    (closed,) = closed_lots
    assert closed.days_held == 0
