from datetime import date
import io
from typing import Any, Iterable

from openpyxl.utils import get_column_letter
import pandas as pd
import streamlit as st

BUTTON_KEY = "export_summary_button"
# Sidebar container the Portfolio page fills once its snapshot is loaded
SLOT_KEY = "_export_summary_slot"
SHEET_NAME = "Summary"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MONEY_FORMAT = "#,##0.00"
PERCENT_FORMAT = "0.00%"
QUANTITY_FORMAT = "#,##0.####"
DATE_FORMAT = "yyyy-mm-dd"

# header -> (row field, number format, column width)
COLUMNS: dict[str, tuple[str, str | None, int]] = {
    "As Of": ("as_of", DATE_FORMAT, 12),
    "Account Number": ("account_number", None, 18),
    "Account Type": ("account_type", None, 14),
    "Asset Type": ("asset_type", None, 16),
    "Symbol": ("symbol", None, 24),
    "Security Name": ("name", None, 44),
    "Currency": ("currency", None, 10),
    "Quantity": ("quantity", QUANTITY_FORMAT, 12),
    "Book Value (CAD)": ("book_value", MONEY_FORMAT, 18),
    "Market Value (CAD)": ("market_value", MONEY_FORMAT, 18),
    "Unrealized P/L (CAD)": ("gain", MONEY_FORMAT, 20),
    "Unrealized P/L %": ("gain_pct", PERCENT_FORMAT, 16),
    "Weight": ("weight", PERCENT_FORMAT, 10),
}


def build_summary_workbook(rows: Iterable[dict[str, Any]], as_of: date) -> bytes:
    """One-sheet workbook with the fixed export columns, one row per constituent."""
    records = [
        {
            header: as_of if field == "as_of" else row.get(field)
            for header, (field, _fmt, _width) in COLUMNS.items()
        }
        for row in rows
    ]
    frame = pd.DataFrame(records, columns=list(COLUMNS))

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=SHEET_NAME, index=False)
        sheet = writer.sheets[SHEET_NAME]
        sheet.freeze_panes = "A2"
        for idx, (_field, number_format, width) in enumerate(COLUMNS.values(), start=1):
            letter = get_column_letter(idx)
            sheet.column_dimensions[letter].width = width
            if number_format:
                for cell in sheet[letter][1:]:
                    cell.number_format = number_format
    return buffer.getvalue()


def export_file_name(scope_number: str | None, as_of: date) -> str:
    return f"portfolio_summary_{scope_number or 'ALL'}_{as_of.isoformat()}.xlsx"


def render_export_summary_button(
    rows: list[dict[str, Any]] | None, scope_number: str | None = None
) -> None:
    """Download button for the Portfolio page's constituents as a workbook.

    `rows` is None off the Portfolio page (button disabled); `scope_number` is
    the account number for a single-account scope. Privacy toggles are
    ignored: the file always has real values.
    """
    label = "Export Summary"
    icon = ":material/download:"
    if rows is None:
        st.button(
            label,
            icon=icon,
            type="secondary",
            key=BUTTON_KEY,
            width="stretch",
            disabled=True,
            help="Open the Portfolio page to export its holdings",
        )
        return

    as_of = date.today()
    st.download_button(
        label,
        data=lambda: build_summary_workbook(rows, as_of),
        file_name=export_file_name(scope_number, as_of),
        mime=XLSX_MIME,
        icon=icon,
        type="secondary",
        key=BUTTON_KEY,
        width="stretch",
        on_click="ignore",
        disabled=not rows,
        help="Excel summary of the holdings and cash shown on the Portfolio page",
    )
