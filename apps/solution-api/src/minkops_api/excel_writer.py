"""Legacy watermark test binding over the shared Excel connector."""

from pathlib import Path

from minkops_connectors.excel import append_rows

APP_DIR = Path(__file__).resolve().parents[2]
EXCEL_DIR = APP_DIR / "data/excel"
EXCEL_FILE = EXCEL_DIR / "watermark_data.xlsx"
COLUMNS = ["date", "time", "latitude", "longitude", "address", "altitude"]


def save_watermarks_to_excel(watermarks):
    return append_rows(
        EXCEL_FILE,
        "Watermark Data",
        COLUMNS,
        ([watermark.get(column) for column in COLUMNS] for watermark in watermarks),
    )
