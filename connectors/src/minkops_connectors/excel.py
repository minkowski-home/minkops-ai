"""Read-only Excel inspection: validated workbooks, header projections and mapped bounds."""

from datetime import date, datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.table import Table, TableColumn

MAX_CELLS = 250_000


def open_workbook(content):
    try:
        archive = ZipFile(BytesIO(content))
    except (BadZipFile, OSError) as error:
        raise ValueError("The selected workbook is not a valid .xlsx file.") from error
    with archive:
        if sum(item.file_size for item in archive.infolist()) > 80_000_000:
            raise ValueError("Workbook expands beyond the supported size.")
        # openpyxl cannot safely round-trip every Excel extension.
        if any(
            "/slicer" in n or "/pivot" in n or "/activeX" in n or "/externalLink" in n
            for n in archive.namelist()
        ):
            raise ValueError(
                "Pivot, slicer, ActiveX and external-link workbooks are not supported yet."
            )
    w = load_workbook(BytesIO(content), data_only=False)
    if sum(s.max_row * s.max_column for s in w) > MAX_CELLS:
        raise ValueError("Workbook exceeds the supported cell limit.")
    return w


def value_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def inspect_workbook(content):
    return [
        {
            "sheet": s.title,
            "row_count": s.max_row,
            "column_count": s.max_column,
            "tables": [{"name": t.name, "range": t.ref} for t in s.tables.values()],
            "rows": [[value_json(v) for v in row] for row in list(s.values)[:50]],
        }
        for s in open_workbook(content)
    ]


def schema_projection(content, observed=None):
    """Validate a header-only receipt and rebuild it without opaque package parts.

    Untabled sheets have at most one declared candidate in the first ten rows;
    named table headers are authoritative. Business interpretation is reviewed
    separately. Preserve formula text without cached results. Reject business rows, links and comments.
    """
    original = open_workbook(content)
    if observed is None:
        observed = {
            "sheets": [
                {
                    "sheet": s.title,
                    "tables": [{"name": t.name, "range": t.ref} for t in s.tables.values()],
                    "preview": [
                        {"row": row[0].row, "values": [c.value for c in row]}
                        for row in s
                        if any(c.value is not None and c.data_type != "f" for c in row)
                    ],
                }
                for s in original
            ]
        }
    sheets = observed.get("sheets") if isinstance(observed, dict) else None
    if (
        not isinstance(sheets, list)
        or len(sheets) > 100
        or [s.get("sheet") for s in sheets if isinstance(s, dict)] != original.sheetnames
    ):
        raise ValueError("Schema must account for every worksheet.")
    projected = Workbook()
    projected.remove(projected.active)
    layouts = []
    for source, observation in zip(original, sheets, strict=True):
        headers = observation.get("preview", [])
        if not isinstance(headers, list) or any(
            not isinstance(h, dict) or type(h.get("row")) is not int for h in headers
        ):
            raise ValueError("Invalid schema headers.")
        declared = {h["row"] for h in headers}
        tables = list(source.tables.values())
        expected = {range_boundaries(t.ref)[1] for t in tables}
        if tables:
            if declared != expected or any(t.headerRowCount != 1 for t in tables):
                raise ValueError("Schema headers must match named tables.")
        elif len(headers) > 1 or any(not 1 <= row <= 10 for row in declared):
            raise ValueError("Confirm a single candidate header in the first ten rows.")
        target = projected.create_sheet(source.title)
        target.sheet_state = source.sheet_state
        formulas = []
        for row in source:
            for cell in row:
                if cell.value is None:
                    continue
                if cell.data_type == "f" and not cell.comment and not cell.hyperlink:
                    if not isinstance(cell.value, str):
                        raise ValueError("Unsupported array formula; discovery needs attention.")
                    target.cell(cell.row, cell.column, cell.value)
                    formulas.append({"cell": cell.coordinate, "formula": cell.value[1:]})
                    continue
                if (
                    cell.row not in declared
                    or not isinstance(cell.value, str)
                    or cell.data_type == "f"
                    or cell.comment
                    or cell.hyperlink
                ):
                    raise ValueError(
                        "Source Discovery accepts headers only; refresh records through the workflow."
                    )
                target.cell(cell.row, cell.column, cell.value)
        if "formulas" in observation and observation["formulas"] != formulas:
            raise ValueError("Formula definitions do not match the workbook.")
        canonical_headers = [
            {"row": r, "values": [c.value for c in target[r]]} for r in sorted(declared)
        ]
        if headers != canonical_headers:
            raise ValueError("Declared headers do not match the schema workbook.")
        canonical_tables = []
        for table in tables:
            columns = [c.name for c in table.tableColumns]
            clean = Table(displayName=table.name, ref=table.ref)
            clean.tableColumns = [
                TableColumn(id=i + 1, name=name) for i, name in enumerate(columns)
            ]
            target.add_table(clean)
            canonical_tables.append(
                {
                    "name": table.name,
                    "range": table.ref,
                    "header_row": range_boundaries(table.ref)[1],
                    "columns": columns,
                }
            )
        if {t["name"]: t["range"] for t in observation.get("tables", [])} != {
            t.name: t.ref for t in tables
        }:
            raise ValueError("Schema tables do not match the workbook.")
        for merged in source.merged_cells.ranges:
            target.merge_cells(str(merged))
        layouts.append(
            {
                "sheet": source.title,
                "state": source.sheet_state,
                "rows": source.max_row,
                "columns": source.max_column,
                "tables": canonical_tables,
                "merged_ranges": [str(r) for r in source.merged_cells.ranges],
                "preview": canonical_headers,
                "formulas": formulas,
                "reference_rows": [],
            }
        )
    buffer = BytesIO()
    projected.save(buffer)
    return buffer.getvalue(), {"format": "xlsx", "sheets": layouts, "defined_names": []}


def mapping_bounds(sheet, mapping):
    """Resolve an agent-selected table, never infer it from column names."""
    if mapping.get("table"):
        if mapping["table"] not in sheet.tables:
            raise ValueError("Catalog refers to a missing Excel table.")
        table = sheet.tables[mapping["table"]]
        bounds = range_boundaries(table.ref)
        if bounds[1] != mapping["header_row"] or table.headerRowCount == 0:
            raise ValueError("Mapped header must match the selected table header.")
        if table.totalsRowCount:
            raise ValueError("Tables with totals rows are not supported yet.")
        return bounds
    if sheet.tables and mapping["role"] != "ignore":
        raise ValueError("Choose the named Excel table explicitly for sheets containing tables.")
    return 1, mapping["header_row"], sheet.max_column, sheet.max_row
