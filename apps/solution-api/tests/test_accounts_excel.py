"""Protect existing workbook content and reject ambiguous or unsafe writes."""

import unittest
from io import BytesIO

from minkops_api.accounts_excel import apply_records, inspect_workbook, validate_catalog
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table


def workbook():
    w = Workbook()
    s = w.active
    s.title = "Bills"
    s.append(["Company records"])
    s.append(["Invoice", "Vendor", "Amount", "Computed"])
    s.append(["A-1", "Acme", 12, "=C3*2"])
    s["A3"].number_format = "@"
    w.create_sheet("Other")["A1"] = "Keep me"
    b = BytesIO()
    w.save(b)
    return b.getvalue()


def catalog():
    return {
        "sheets": [
            {
                "file_id": "f1",
                "sheet": "Bills",
                "header_row": 2,
                "role": "destination",
                "key_columns": ["Invoice", "Vendor"],
                "columns": [
                    {
                        "name": "Invoice",
                        "type": "string",
                        "concept": "invoice_number",
                        "required": True,
                    },
                    {"name": "Vendor", "type": "string", "concept": "vendor", "required": True},
                    {"name": "Amount", "type": "number", "concept": "total", "required": True},
                    {"name": "Computed", "type": "number", "concept": "", "required": False},
                ],
            }
        ]
    }


class ExcelTests(unittest.TestCase):
    def test_proposed_semantic_conflicts_are_reviewable_but_not_confirmable(self):
        candidate = catalog()
        candidate["sheets"][0]["columns"][1]["concept"] = "invoice_number"
        validate_catalog(candidate, {"f1": workbook()}, review_proposal=True)
        with self.assertRaises(ValueError):
            validate_catalog(candidate, {"f1": workbook()})

    def test_unrecognized_destination_is_reviewable_and_cannot_be_guessed(self):
        from minkops_api.accounts_store import check_records

        result = {
            "records": [],
            "findings": [],
            "unresolved": [
                {
                    "source_file_id": "bill",
                    "reason": "Two registers have equally plausible purposes.",
                }
            ],
        }
        checked = check_records(result, catalog(), ["bill"], {"f1": workbook()}, [])
        self.assertEqual(checked["unresolved"][0]["reason"], result["unresolved"][0]["reason"])
        with self.assertRaises(ValueError):
            check_records(
                {"records": [], "findings": []}, catalog(), ["bill"], {"f1": workbook()}, []
            )

    def test_workbook_without_optional_security_element_can_be_saved(self):
        w = load_workbook(BytesIO(workbook()))
        w.security = None
        b = BytesIO()
        w.save(b)
        output, _ = apply_records(
            b.getvalue(),
            catalog()["sheets"][0],
            [{"data": {"Invoice": "A-2", "Vendor": "Acme", "Amount": 24}}],
        )
        self.assertEqual(load_workbook(BytesIO(output))["Bills"]["A4"].value, "A-2")

    def test_named_table_routing_preserves_adjacent_table_and_footer(self):
        w = Workbook()
        s = w.active
        s.title = "Bills"
        for row in [("Invoice", "Vendor", "Amount"), ("A-1", "Acme", 12)]:
            s.append(row)
        for row in [("Invoice", "Vendor", "Amount"), ("A-1", "Other", 99)]:
            for col, value in enumerate(row, 5):
                s.cell(1 if row[0] == "Invoice" else 2, col, value)
        s.add_table(Table(displayName="Purchases", ref="A1:C2"))
        s.add_table(Table(displayName="OtherPurchases", ref="E1:G2"))
        s["A8"] = "Unrelated footer"
        b = BytesIO()
        w.save(b)
        m = catalog()["sheets"][0]
        m.update(table="Purchases", header_row=1)
        m["columns"] = m["columns"][:3]
        validate_catalog({"sheets": [m]}, {"f1": b.getvalue()})
        out, changes = apply_records(
            b.getvalue(), m, [{"data": {"Invoice": "A-2", "Vendor": "Acme", "Amount": 24}}]
        )
        saved = load_workbook(BytesIO(out))["Bills"]
        self.assertEqual(changes[0]["row"], 3)
        self.assertEqual(saved.tables["Purchases"].ref, "A1:C3")
        self.assertEqual(saved.tables["OtherPurchases"].ref, "E1:G2")
        self.assertEqual(saved["G2"].value, 99)
        self.assertEqual(saved["A8"].value, "Unrelated footer")
        self.assertEqual(inspect_workbook(out)[0]["tables"][0]["name"], "Purchases")
        saved["A4"] = "Do not overwrite"
        b = BytesIO()
        saved.parent.save(b)
        with self.assertRaises(ValueError):
            apply_records(
                b.getvalue(), m, [{"data": {"Invoice": "A-3", "Vendor": "Acme", "Amount": 24}}]
            )

    def test_headers_must_match_real_workbook(self):
        c = catalog()
        c["sheets"][0]["columns"][0]["name"] = "Invented"
        with self.assertRaises(ValueError):
            validate_catalog(c, {"f1": workbook()})

    def test_discovery_preserves_non_first_header_rows(self):
        inventory = inspect_workbook(workbook())
        self.assertEqual(inventory[0]["rows"][1][0], "Invoice")
        validate_catalog(catalog(), {"f1": workbook()})

    def test_append_preserves_formulas_styles_and_other_sheets(self):
        output, changes = apply_records(
            workbook(),
            catalog()["sheets"][0],
            [{"data": {"Invoice": "A-2", "Vendor": "Acme", "Amount": 24}, "operation": "append"}],
        )
        w = load_workbook(BytesIO(output))
        self.assertEqual(w["Bills"]["A4"].value, "A-2")
        self.assertEqual(w["Bills"]["D3"].value, "=C3*2")
        self.assertEqual(w["Bills"]["D4"].value, "=C4*2")
        self.assertEqual(w["Other"]["A1"].value, "Keep me")
        self.assertEqual(changes[0]["row"], 4)

    def test_duplicate_append_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_records(
                workbook(),
                catalog()["sheets"][0],
                [
                    {
                        "data": {"Invoice": "A-1", "Vendor": "Acme", "Amount": 24},
                        "operation": "append",
                    }
                ],
            )

    def test_edit_requires_exact_unique_key_and_preserves_other_cells(self):
        output, _ = apply_records(
            workbook(),
            catalog()["sheets"][0],
            [{"data": {"Invoice": "A-1", "Vendor": "Acme", "Amount": 25}, "operation": "update"}],
        )
        s = load_workbook(BytesIO(output))["Bills"]
        self.assertEqual(s["C3"].value, 25)
        self.assertEqual(s["D3"].value, "=C3*2")
        with self.assertRaises(ValueError):
            apply_records(
                workbook(),
                catalog()["sheets"][0],
                [{"data": {"Invoice": "absent", "Vendor": "Acme"}, "operation": "update"}],
            )

    def test_formula_injection_and_unknown_columns_are_rejected(self):
        for data in [
            {"Invoice": "=cmd()", "Vendor": "X", "Amount": 2},
            {"Invoice": "A-2", "Vendor": "X", "Amount": 2, "Extra": 4},
        ]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                apply_records(
                    workbook(), catalog()["sheets"][0], [{"data": data, "operation": "append"}]
                )

    def test_wrong_types_and_missing_required_values_are_rejected(self):
        for data in [{"Invoice": "A-2", "Vendor": "X", "Amount": "many"}, {"Invoice": "A-2"}]:
            with self.assertRaises(ValueError):
                apply_records(
                    workbook(), catalog()["sheets"][0], [{"data": data, "operation": "append"}]
                )
