"""Voucher families come from discovered voucher types, never a hard-coded name."""

from minkops_platform.accounts.voucher_types import base_types

PURCHASE = {"@_NAME": "Purchase", "@_RESERVEDNAME": "Purchase", "PARENT": "Purchase", "GUID": "vt-p", "ALTERID": "1"}
GST = {"@_NAME": "Purchase GST", "@_RESERVEDNAME": "", "PARENT": {"#text": "Purchase", "@_TYPE": "String"},
       "GUID": "vt-g", "ALTERID": " 5", "ISACTIVE": "Yes"}
OLD = {"@_NAME": "Purchase Old", "PARENT": "Purchase", "GUID": "vt-o", "ISACTIVE": "No"}
BRANCH = {"@_NAME": "Purchase GST Mumbai", "PARENT": "purchase gst", "GUID": "vt-m"}
ORDER = {"@_NAME": "Purchase Order", "@_RESERVEDNAME": "Purchase Order", "PARENT": "Purchase Order", "GUID": "vt-po"}
JOURNAL = {"@_NAME": "Journal", "@_RESERVEDNAME": "Journal", "GUID": "vt-j"}
LOOP = [{"@_NAME": "Loop A", "PARENT": "Loop B", "GUID": "l1"}, {"@_NAME": "Loop B", "PARENT": "Loop A", "GUID": "l2"}]
RENAMED = {"@_NAME": "Purchases", "@_RESERVEDNAME": "Purchase", "PARENT": "Purchases", "GUID": "vt-r"}


def test_base_type_follows_reserved_names_and_parent_chains():
    bases = base_types([PURCHASE, GST, OLD, BRANCH, ORDER, JOURNAL, *LOOP, RENAMED])
    assert bases["purchase gst"] == "Purchase"
    assert bases["purchase gst mumbai"] == "Purchase"
    assert bases["purchase order"] == "Purchase Order"
    assert bases["purchases"] == "Purchase"
    assert bases["journal"] == "Journal"
    assert bases["loop a"] is None and bases["loop b"] is None
