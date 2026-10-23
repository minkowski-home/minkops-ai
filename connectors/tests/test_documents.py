"""Bill files as pages: text layers where the PDF has them, a bounded image for every page."""

import io
import unittest
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from minkops_connectors.documents import MAX_PAGES, MAX_SIDE, pages

SYNTHETIC = Path(__file__).resolve().parents[2] / "packages/fixtures/synthetic/bills"


def text_pdf(*lines):
    """A one-page PDF whose text layer holds these lines, one below another."""
    shown = " ".join(f"({line}) Tj 0 -20 Td" for line in lines)
    stream = f"BT /F1 11 Tf 72 760 Td {shown} ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    body, offsets = b"%PDF-1.4\n", []
    for number, content in enumerate(objects, 1):
        offsets.append(len(body))
        body += b"%d 0 obj\n" % number + content + b"\nendobj\n"
    xref = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return body + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref


class PagesTest(unittest.TestCase):
    def test_a_pdf_keeps_its_text_lines_and_a_scan_still_renders_every_page(self):
        [page] = pages(text_pdf("Invoice No INV-17", "A4 Copier Paper 40 245.00 9800.00",
                                "Box File Heavy Duty 60 118.50 7110.00"), ".pdf")
        # Table rows stay on their own lines, so a description never runs into the next row.
        self.assertEqual(page["text"].split("\n"), ["Invoice No INV-17", "A4 Copier Paper 40 245.00 9800.00",
                                                     "Box File Heavy Duty 60 118.50 7110.00"])
        scan = next(SYNTHETIC.glob("2901*.pdf"))
        read = pages(scan.read_bytes(), ".pdf")
        self.assertEqual([(p["page"], p["text"]) for p in read], [(1, ""), (2, "")])
        for page in read:
            with Image.open(io.BytesIO(page["image"])) as image:
                self.assertEqual((image.format, image.size), ("JPEG", (page["width"], page["height"])))
                self.assertLessEqual(max(image.size), MAX_SIDE)

    def test_an_image_bill_is_one_page_with_no_text_layer(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (3000, 1500), (255, 255, 255, 255)).save(buffer, format="PNG")
        [page] = pages(buffer.getvalue(), ".PNG")
        self.assertEqual((page["page"], page["text"], page["width"], page["height"]), (1, "", MAX_SIDE, 900))

    def test_unreadable_oversized_and_unsupported_files_are_refused_with_a_reason(self):
        with self.assertRaisesRegex(ValueError, "could not be opened"):
            pages(b"%PDF-1.7 truncated", ".pdf")
        long = pdfium.PdfDocument.new()
        for _ in range(MAX_PAGES + 1):
            long.new_page(595, 842)
        buffer = io.BytesIO()
        long.save(buffer)
        with self.assertRaisesRegex(ValueError, "at most 12 pages"):
            pages(buffer.getvalue(), ".pdf")
        with self.assertRaisesRegex(ValueError, "could not be read"):
            pages(b"not an image", ".jpg")
        with self.assertRaisesRegex(ValueError, "PDF, PNG, JPEG or WebP"):
            pages(b"a,b\n", ".csv")
