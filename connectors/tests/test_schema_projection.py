from io import BytesIO
from unittest import TestCase

from openpyxl import Workbook
from minkops_connectors.excel import schema_projection, open_workbook


class SchemaProjectionTests(TestCase):
    def test_receipt_rejects_business_cells_and_canonicalizes_header_metadata(self):
        workbook = Workbook()
        workbook.active.title = "Bills"
        workbook.active.append(["Invoice", "Supplier"])
        workbook.active.append(["private invoice", "private supplier"])
        observed = {
            "sheets": [
                {
                    "sheet": "Bills",
                    "tables": [],
                    "preview": [{"row": 1, "values": ["Invoice", "Supplier"]}],
                }
            ]
        }
        buf = BytesIO()
        workbook.save(buf)
        with self.assertRaisesRegex(ValueError, "headers only"):
            schema_projection(buf.getvalue(), observed)
        workbook.active.delete_rows(2)
        workbook.properties.creator = "private author"
        buf = BytesIO()
        workbook.save(buf)
        content, metadata = schema_projection(buf.getvalue(), observed)
        self.assertNotEqual(open_workbook(content).properties.creator, "private author")
        self.assertEqual(metadata["sheets"][0]["preview"], observed["sheets"][0]["preview"])
        self.assertEqual(metadata["sheets"][0]["reference_rows"], [])
