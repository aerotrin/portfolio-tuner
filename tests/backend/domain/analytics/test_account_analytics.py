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
        ]
    )

    open_lots, closed_lots, cash_flows = run_records_parser(tx)

    assert len(open_lots) == 0
    assert len(closed_lots) == 0
    assert len(cash_flows) == 3

    contrib, dividend, fee = cash_flows
    assert contrib.category == Category.CASH
    assert contrib.settlement_date == date(2024, 1, 4)

    assert dividend.category == Category.INCOME
    assert dividend.settlement_date is None

    assert fee.category == Category.EXPENSE
    assert fee.settlement_date is None
