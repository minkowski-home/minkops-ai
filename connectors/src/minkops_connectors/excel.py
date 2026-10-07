"""Excel byte inspection and safe edits; business validation belongs to the caller."""

from copy import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
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
    separately. Never accept row samples, formulas, links or comments as schema.
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
                        if any(c.value is not None for c in row)
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
        for row in source:
            for cell in row:
                if cell.value is None:
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
                "formulas": [],
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


def mapped_columns(sheet, mapping):
    a, b, c, _ = mapping_bounds(sheet, mapping)
    return {
        str(sheet.cell(b, i).value).strip(): i
        for i in range(a, c + 1)
        if sheet.cell(b, i).value is not None
    }


def sheet_records(content, mapping):
    s = open_workbook(content)[mapping["sheet"]]
    columns = mapped_columns(s, mapping)
    _, b, _, d = mapping_bounds(s, mapping)
    return [
        {
            "row": row,
            "data": {
                c["name"]: value_json(s.cell(row, columns[c["name"]]).value)
                for c in mapping["columns"]
            },
        }
        for row in range(b + 1, d + 1)
        if any(s.cell(row, columns[c["name"]]).value is not None for c in mapping["columns"])
    ]


def apply_records(content, mapping, records, *, validate_record):
    """Apply a reviewed plan to one sheet; preserve unrelated cells and formulas.

    Append refuses duplicate keys. Update requires exactly one existing key match.
    Writes happen to an in-memory copy; the browser owns the actual local commit.
    """
    w = open_workbook(content)
    s = w[mapping["sheet"]]
    if s.protection.sheet or (w.security and w.security.lockStructure):
        raise ValueError("Protected workbooks cannot be edited.")
    columns = mapped_columns(s, mapping)
    changes = []
    for record in records:
        data = record["data"]
        validate_record(mapping, data)
        keys = mapping["key_columns"]
        if any(data.get(k) is None or data.get(k) == "" for k in keys):
            raise ValueError("Record keys must be complete.")
        a, b, c, d = mapping_bounds(s, mapping)
        match_data = record.get("match_data", data) if record.get("operation") == "update" else data
        if any(match_data.get(k) in (None, "") for k in keys):
            raise ValueError("Correction keys must be complete.")
        matches = [
            r
            for r in range(b + 1, d + 1)
            if all(
                str(value_json(s.cell(r, columns[k]).value)).strip().casefold()
                == str(match_data[k]).strip().casefold()
                for k in keys
            )
        ]
        operation = record.get("operation", "append")
        if operation == "append":
            if matches:
                raise ValueError("Duplicate record: choose an explicit edit after review.")
            row = d + 1
            if mapping.get("table"):
                if any(s.cell(row, i).value is not None for i in range(a, c + 1)):
                    raise ValueError(
                        "Table expansion would overwrite existing cells. Review the destination layout."
                    )
                for other in s.tables.values():
                    x, y, z, last = range_boundaries(other.ref)
                    if other.name != mapping["table"] and y <= row <= last and a <= z and c >= x:
                        raise ValueError("Table expansion would overlap another table.")
            previous = row - 1
            for i in range(a, c + 1):
                src, target = s.cell(previous, i), s.cell(row, i)
                target._style = copy(src._style)
                if src.data_type == "f":
                    target.value = Translator(src.value, origin=src.coordinate).translate_formula(
                        target.coordinate
                    )
        elif operation == "update":
            if len(matches) != 1:
                raise ValueError("Editing requires exactly one existing record with matching keys.")
            row = matches[0]
        else:
            raise ValueError("Unsupported record operation.")
        for name, value in data.items():
            cell = s.cell(row, columns[name])
            if cell.data_type == "f":
                if value is not None:
                    raise ValueError(f"Cannot overwrite computed column {name}.")
                continue
            cell.value = value
        if mapping.get("table") and operation == "append":
            table = s.tables[mapping["table"]]
            table.ref = f"{get_column_letter(a)}{b}:{get_column_letter(c)}{row}"
            if table.autoFilter:
                table.autoFilter.ref = table.ref
        changes.append(
            {
                "sheet": s.title,
                "table": mapping.get("table"),
                "row": row,
                "operation": operation,
                "data": data,
            }
        )
    output = BytesIO()
    w.save(output)
    # Reopen and inspect each written value before publishing a write plan.
    saved = open_workbook(output.getvalue())[s.title]
    for change in changes:
        for key, value in change["data"].items():
            actual = saved.cell(change["row"], columns[key])
            if actual.data_type != "f" and actual.value != (None if value == "" else value):
                raise ValueError("Workbook verification failed.")
    return output.getvalue(), changes


def append_rows(path: Path, sheet_name: str, columns: list[str], rows):
    """Legacy append/create operation with an explicit destination and layout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        workbook = load_workbook(path)
        sheet = workbook[sheet_name]
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        sheet.append(columns)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path
