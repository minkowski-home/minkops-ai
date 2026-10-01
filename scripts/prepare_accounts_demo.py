"""Prepare disposable synthetic inputs without overwriting a tested workspace.

Run with `uv run --all-packages --with pymupdf python scripts/prepare_accounts_demo.py`.
"""

import shutil
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1] / "apps/solution-api/data"


def main():
    source = ROOT / "mock-bills"
    destination = ROOT / "mock-workspace"
    if destination.exists():
        raise SystemExit(
            "Mock workspace already exists; choose a new disposable workspace rather than overwriting it."
        )
    required = [source / "reference", source / "pdf"]
    if any(not path.exists() for path in required):
        raise SystemExit("Existing synthetic mock-bills samples are required.")
    shutil.copytree(source / "reference", destination / "reference")
    bills = destination / "bills"
    bills.mkdir()
    for pattern in ("01_*.pdf", "02_*.pdf", "03_*.pdf"):
        for pdf in (source / "pdf").glob(pattern):
            shutil.copy2(pdf, bills / pdf.name)
    scanned = next((source / "pdf").glob("04_*.pdf"))
    with fitz.open(scanned) as document:
        document[0].get_pixmap(dpi=140).save(bills / "04_kesar_stone_scanned.png")
    print(f"Connect this synthetic folder in the app: {destination}")


if __name__ == "__main__":
    main()
