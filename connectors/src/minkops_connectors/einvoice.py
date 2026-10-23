"""Signed e-invoice QR codes: the invoice one registers, and who signed it.

An Indian e-invoice carries a QR code its Invoice Registration Portal (IRP)
signed: a JWS (RS256) whose header names the signing certificate by its SHA-1
thumbprint (`kid`, and base64url-encoded as `x5t`), and whose payload's `data`
holds the registered invoice. That covers the seller and buyer GSTINs, the
document type, number and date, the total value and the IRN, with its date in
newer codes.

Each IRP publishes its signing keys per IRN generation period. Those Minkops
trusts are pinned in `einvoice_signers/`, each with its official source in
`signers.json`. Sandbox keys are never trusted: what they sign was never
registered. A code is one of three things:

- `verified`: signed by a pinned key;
- `altered`: it names a pinned certificate, but its signature does not
  verify;
- `unverified`: its key is not pinned (an IRP or rotation not pinned yet). It
  is still an exact machine reading of the invoice, but no proof the IRP
  registered it.
"""

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import cache
from importlib import resources

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

KINDS = {"INV": "invoice", "CRN": "credit_note", "DBN": "debit_note"}
GSTIN = re.compile(r"^[0-9]{2}[A-Z0-9]{13}$")
# Keys hand over on a shared boundary day; a code dated either side of it is that key's.
OVERLAP = timedelta(days=1)


@dataclass(frozen=True)
class Signer:
    """One pinned IRP signing key and the IRN generation period it signed."""

    irp: str
    key: object
    sha1: str | None
    irns: tuple


@cache
def signers():
    """The pinned production signing keys of the IRPs Minkops verifies."""
    folder = resources.files("minkops_connectors") / "einvoice_signers"
    pinned = []
    for entry in json.loads((folder / "signers.json").read_text()):
        pem = (folder / entry["file"]).read_bytes()
        key = (x509.load_pem_x509_certificate(pem).public_key() if b"CERTIFICATE" in pem
               else serialization.load_pem_public_key(pem))
        pinned.append(Signer(entry["irp"], key, entry["sha1"], tuple(_day(value) for value in entry["irns"])))
    return tuple(pinned)


def read(code, trusted=None):
    """The e-invoice a QR code registers, or None when the code is no signed e-invoice.

    Returns {status, signer, seller_gstin, buyer_gstin, kind, number, date,
    total_cents, irn, irn_date}; dates are ISO, and `signer` names the IRP
    whose pinned key verified the code, or should have.
    """
    parts = code.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        header, payload, signature = json.loads(_b64(parts[0])), json.loads(_b64(parts[1])), _b64(parts[2])
        data = json.loads(payload["data"]) if isinstance(payload.get("data"), str) else payload.get("data")
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error):
        return None
    if not isinstance(header, dict) or header.get("alg") != "RS256" or not isinstance(data, dict):
        return None
    invoice = _invoice(data)
    if invoice is None:
        return None
    status, signer = _verify(f"{parts[0]}.{parts[1]}".encode(), signature, _thumbprint(header),
                             _day(invoice["irn_date"]), signers() if trusted is None else trusted)
    return {"status": status, "signer": signer, **invoice}


def _invoice(data):
    """The registered invoice's identity, or None when the payload is no e-invoice."""
    try:
        issued = datetime.strptime(str(data["DocDt"]), "%d/%m/%Y").date().isoformat()
        total = Decimal(str(data["TotInvVal"]))
    except (KeyError, ValueError, InvalidOperation):
        return None
    irn, number = str(data.get("Irn") or ""), str(data.get("DocNo") or "").strip()
    seller, buyer = str(data.get("SellerGstin") or "").strip().upper(), str(data.get("BuyerGstin") or "").strip().upper()
    if not re.fullmatch(r"[0-9a-f]{64}", irn) or not number or not GSTIN.match(seller) or not total.is_finite():
        return None
    registered = str(data.get("IrnDt") or "")[:10]
    return {"seller_gstin": seller, "buyer_gstin": buyer or None, "kind": KINDS.get(str(data.get("DocTyp"))),
            "number": number, "date": issued, "total_cents": int((total * 100).to_integral_value()), "irn": irn,
            "irn_date": registered if re.fullmatch(r"\d{4}-\d{2}-\d{2}", registered) else None}


def _verify(signed, signature, thumbprint, registered, trusted):
    """(status, signer): the certificate the code names, else a pinned bare key whose period covers it."""
    named = [s for s in trusted if s.sha1 and s.sha1 == thumbprint]
    candidates = named or [s for s in trusted if s.sha1 is None and _covers(s, registered)]
    for signer in candidates:
        try:
            signer.key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            continue
        # A pinned key signs only within its period; outside it, the code proves nothing.
        return ("verified", signer.irp) if _covers(signer, registered) else ("unverified", None)
    return ("altered", named[0].irp) if named else ("unverified", None)


def _covers(signer, registered):
    start, end = signer.irns
    return registered is None or ((start is None or start - OVERLAP <= registered)
                                  and (end is None or registered <= end + OVERLAP))


def _thumbprint(header):
    """The signing certificate's SHA-1 thumbprint as upper hex, from `kid` or `x5t`."""
    kid = str(header.get("kid") or "").upper()
    if re.fullmatch(r"[0-9A-F]{40}", kid):
        return kid
    try:
        return _b64(str(header.get("x5t") or "")).hex().upper() or None
    except (ValueError, binascii.Error):
        return None


def _b64(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _day(value):
    return date.fromisoformat(value) if value else None
