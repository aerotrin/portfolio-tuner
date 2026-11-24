from datetime import date, datetime
import io

from openpyxl import load_workbook
import pytest
from streamlit.testing.v1 import AppTest

import frontend.widgets.export_summary as export

AS_OF = date(2026, 11, 23)

STOCK = {
    "account_number": "ACC-A",
    "account_name": "Alice TFSA",
    "account_type": "TFSA",
    "asset_type": "Stock",
    "symbol": "AAPL",
    "name": "Apple Inc",
    "currency": "USD",
    "quantity": 10,
    "book_value": 1500.0,
    "market_value": 2000.0,
    "gain": 500.0,
    "gain_pct": 0.3333,
    "weight": 0.8,
}
CASH = {
    "account_number": "ACC-A",
    "account_name": "Alice TFSA",
    "account_type": "TFSA",
    "asset_type": "Cash",
    "symbol": "CASH",
    "name": "Cash (CAD)",
    "currency": "CAD",
    "quantity": None,
    "book_value": 500.0,
    "market_value": 500.0,
    "gain": 0.0,
    "gain_pct": None,
    "weight": 0.2,
}


def test_workbook_has_fixed_columns_and_typed_cells():
    book = load_workbook(
        io.BytesIO(export.build_summary_workbook([STOCK, CASH], AS_OF))
    )

    assert book.sheetnames == ["Summary"]
    sheet = book["Summary"]
    header, stock, cash = list(sheet.iter_rows(values_only=True))
    assert list(header) == [
        "As Of",
        "Account Number",
        "Account Type",
        "Asset Type",
        "Symbol",
        "Security Name",
        "Currency",
        "Quantity",
        "Book Value (CAD)",
        "Market Value (CAD)",
        "Unrealized P/L (CAD)",
        "Unrealized P/L %",
        "Weight",
    ]
    assert stock == (
        datetime(2026, 11, 23),
        "ACC-A",
        "TFSA",
        "Stock",
        "AAPL",
        "Apple Inc",
        "USD",
        10,
        1500.0,
        2000.0,
        500.0,
        0.3333,
        0.8,
    )
    # Cash keeps the same columns; quantity and P/L % stay blank
    assert cash[3:8] == ("Cash", "CASH", "Cash (CAD)", "CAD", None)
    assert cash[8:] == (500.0, 500.0, 0.0, None, 0.2)

    assert sheet.freeze_panes == "A2"
    assert sheet["A2"].number_format == "yyyy-mm-dd"
    assert sheet["J2"].number_format == "#,##0.00"
    assert sheet["M2"].number_format == "0.00%"


def test_workbook_with_no_rows_still_has_headers():
    book = load_workbook(io.BytesIO(export.build_summary_workbook([], AS_OF)))
    rows = list(book["Summary"].iter_rows(values_only=True))
    assert len(rows) == 1 and rows[0][0] == "As Of"


def test_file_name_carries_scope_and_date():
    assert (
        export.export_file_name(None, AS_OF) == "portfolio_summary_ALL_2026-11-23.xlsx"
    )
    assert (
        export.export_file_name("ACC-A", AS_OF)
        == "portfolio_summary_ACC-A_2026-11-23.xlsx"
    )


def _app(rows: list[dict] | None, scope_number: str | None) -> None:
    import frontend.widgets.export_summary as export

    export.render_export_summary_button(rows, scope_number)


def _run(rows: list[dict] | None, scope_number: str | None = None) -> AppTest:
    at = AppTest.from_function(_app, args=(rows, scope_number), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_disabled_placeholder_off_the_portfolio_page():
    at = _run(None)
    assert at.button(key="export_summary_button").disabled


@pytest.mark.parametrize("rows", [[STOCK, CASH], []])
def test_download_button_renders_for_a_loaded_portfolio(rows):
    at = _run(rows, "ACC-A")
    assert not at.button
