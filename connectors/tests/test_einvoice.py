"""Signed e-invoice QR codes: what one registers, and whether its IRP's pinned key signed it."""

import base64
import io
import json
import unittest
from datetime import date

import qrcode
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from PIL import Image

from minkops_connectors import einvoice
from minkops_connectors.documents import pages

# NIC's published sample e-invoice (einvoice1.gst.gov.in, Documents/SampleJson.json), signed in August 2020 with
# the key NIC lists for that IRN generation period.
NIC_SAMPLE = (
    "eyJhbGciOiJSUzI1NiIsImtpZCI6IjExNUY0NDI2NjE3QTc5MzhCRTFCQTA2REJFRTkxQTQyNzU4NEVEQUIiLCJ0eXAiOiJKV1Qi"
    "LCJ4NXQiOiJFVjlFSm1GNmVUaS1HNkJ0dnVrYVFuV0U3YXMifQ.eyJkYXRhIjoie1wiU2VsbGVyR3N0aW5cIjpcIjM3QlpOUE05N"
    "DMwTTFLTFwiLFwiQnV5ZXJHc3RpblwiOlwiMDNCWk5QTTk0MzBNMUtMXCIsXCJEb2NOb1wiOlwiQ1RETjIzNDU2XCIsXCJEb2NUe"
    "XBcIjpcIklOVlwiLFwiRG9jRHRcIjpcIjA1LzA4LzIwMjBcIixcIlRvdEludlZhbFwiOjE2NjUwLFwiSXRlbUNudFwiOjEsXCJNY"
    "WluSHNuQ29kZVwiOlwiMzkyMzEwMTBcIixcIklyblwiOlwiYWZkY2MzMmEwZWFhM2EwNTRjZmZjZDI1MTg4NGQzZTNmNGY3MjZiN"
    "zVjODk0M2U3ZDM1ZmJhYmM4MmYwNWQ4YVwifSIsImlzcyI6Ik5JQyJ9.Wb0zhfPKW2dRY4ocTbDnD4Bspz4cZoQ9To_HmWxA2xmV"
    "d-VBK_57H-9AW-wTNvjFyFwMx0PWV_4CQjcajxTUjsA9DxOe4r6XCi86XEuXmXDt49gCNY3dZTeoZyueyYAOsRoOZ4ETtDuqvHQG"
    "DVsc7Lyaj9qMbyn0NnSH_KwUUrK6Qt8tmcqocv0CvCKZEN5NmeICseCEh0ndJSOmK2kb41sQgAjhNq9-xRz8f7oOrWaC6yf9DMPh"
    "YW-Vcux0E9JLABoNtX3Qb326dd0J1BOMUbhIrAt9QdamaMmHKgO1h-3974d7uUBzz4e-6jrclUjZX2XGvH2oXgBwmvgMHwW62Q")
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_IRP = einvoice.Signer("Test IRP", KEY.public_key(), "AB" * 20, (date(2026, 1, 1), date(2026, 12, 31)))
INVOICE = {"SellerGstin": "37ABCDE1234F1Z5", "BuyerGstin": "37PQRST5678K1Z2", "DocNo": "INV/26/101", "DocTyp": "INV",
           "DocDt": "02/06/2026", "TotInvVal": 11800.5, "ItemCnt": 2, "MainHsnCode": "8431", "Irn": "a" * 64,
           "IrnDt": "2026-06-02 10:15:00"}


def encoded(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


def signed(data, key=KEY, header=None):
    """A code as an IRP signs one: RS256 over the header and a payload whose `data` is the invoice, as text."""
    head, body = encoded(header or {"alg": "RS256", "kid": "AB" * 20, "typ": "JWT"}), encoded({"data": json.dumps(data),
                                                                                              "iss": "TEST"})
    signature = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


class SignedQrTest(unittest.TestCase):
    def test_nics_published_sample_verifies_against_its_pinned_key(self):
        self.assertEqual(einvoice.read(NIC_SAMPLE), {
            "status": "verified", "signer": "NIC IRP 1", "seller_gstin": "37BZNPM9430M1KL",
            "buyer_gstin": "03BZNPM9430M1KL", "kind": "invoice", "number": "CTDN23456", "date": "2020-08-05",
            "total_cents": 1665000, "irn": "afdcc32a0eaa3a054cffcd251884d3e3f4f726b75c8943e7d35fbabc82f05d8a",
            "irn_date": None})
        # The same code with another total keeps NIC's signature, which no longer matches: it was altered.
        head, body, signature = NIC_SAMPLE.split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        payload["data"] = payload["data"].replace('"TotInvVal":16650', '"TotInvVal":16950')
        altered = einvoice.read(f"{head}.{encoded(payload)}.{signature}")
        self.assertEqual((altered["status"], altered["signer"], altered["total_cents"]), ("altered", "NIC IRP 1", 1695000))

    def test_a_key_minkops_has_not_pinned_or_one_outside_its_period_proves_nothing(self):
        code = signed(INVOICE)
        self.assertEqual(einvoice.read(code, trusted=(TEST_IRP,))["status"], "verified")
        self.assertEqual(einvoice.read(code, trusted=(TEST_IRP,))["date"], "2026-06-02")
        # Every pinned IRP key is someone else's: still a reading of the invoice, but no proof of registration.
        self.assertEqual((einvoice.read(code)["status"], einvoice.read(code)["number"]), ("unverified", "INV/26/101"))
        late = signed({**INVOICE, "IrnDt": "2027-02-01 09:00:00"})
        self.assertEqual(einvoice.read(late, trusted=(TEST_IRP,))["status"], "unverified")
        # A certificate named by x5t is found as by kid.
        thumb = base64.urlsafe_b64encode(bytes.fromhex("AB" * 20)).rstrip(b"=").decode()
        self.assertEqual(einvoice.read(signed(INVOICE, header={"alg": "RS256", "x5t": thumb}), trusted=(TEST_IRP,))[
            "status"], "verified")

    def test_codes_that_are_no_signed_e_invoice_are_left_alone(self):
        for code in ("upi://pay?pa=supplier@bank&am=1180", signed({**INVOICE, "Irn": ""}),
                     signed(INVOICE, header={"alg": "HS256", "kid": "AB" * 20}), "a.b.c", "not even close"):
            with self.subTest(code=code[:30]):
                self.assertIsNone(einvoice.read(code, trusted=(TEST_IRP,)))

    def test_a_signed_code_printed_on_a_pdf_or_an_image_page_is_decoded(self):
        sticker = qrcode.make(NIC_SAMPLE, box_size=4, border=4).get_image().convert("RGB")
        page = Image.new("RGB", (1240, 1754), "white")
        page.paste(sticker, (700, 1100))
        for suffix, save in ((".pdf", {"format": "PDF", "resolution": 150}), (".png", {"format": "PNG"})):
            buffer = io.BytesIO()
            page.save(buffer, **save)
            with self.subTest(suffix=suffix):
                [read] = pages(buffer.getvalue(), suffix)
                self.assertEqual(read["codes"], [NIC_SAMPLE])
