"""Voucher families come from discovered voucher types, never a hard-coded name.

Practices book under their own types (*Purchase GST*, *Payment - HDFC*). A
type's base is Tally's predefined type: its RESERVEDNAME when Tally marks it
predefined, otherwise the base of its PARENT, followed by name. The companion
applies the same rule to live masters before every write
(connectors/desktop/src/voucher.js voucherFamilies), so the voucher checked here
and the duplicates found there always agree on a family.
"""

from .client_context import text

MAX_CHAIN = 10


def _name(record):
    return (text(record.get("@_NAME")) or text(record.get("NAME")) or "").strip()


def base_types(records):
    """Each type's predefined base, by casefolded name; None for a broken chain."""
    by_name = {_name(r).casefold(): r for r in records if _name(r)}

    def resolve(name, depth):
        record = by_name.get(name.casefold())
        if record is None:
            return name  # A predefined base the export did not include.
        reserved = (text(record.get("@_RESERVEDNAME")) or "").strip()
        if reserved:
            return reserved
        parent = (text(record.get("PARENT")) or "").strip()
        if not parent or parent.casefold() == name.casefold():
            return _name(record)
        return None if depth >= MAX_CHAIN else resolve(parent, depth + 1)

    return {key: resolve(_name(record), 0) for key, record in by_name.items()}
