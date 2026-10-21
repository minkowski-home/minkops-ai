"""Deterministic practice probes over the mirror, and one-click practice questions.

After every published sync the probes ask how this company keeps its books:
are Receipt Notes in use, do purchase narrations carry receipt-register
numbers, where is the supplier's invoice number recorded, are bank payments
booked to each party's ledger or to one ledger with cost centres, is bill-wise
tracking on. A probe that settles the question records a confirmed structured
entry, a fact about the books with the counts behind it. An inconclusive probe
raises one one-click question per company, and the chosen option becomes the
entry. No question ever blocks a run: only the items that depend on it wait,
and answering releases them.
"""

import re
from collections import Counter
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from minkops_platform import attention

from . import memory, mirror
from .voucher_types import base_types

RECEIPT_REGISTER = re.compile(r"\b(?:DMR|GRN|MRN|GIN|R\.?R\.?)\s*(?:NO\.?|#|:)?\s*[-:]?\s*\d{2,}", re.I)
INVOICE_TOKEN = re.compile(r"\b(?:INV|BILL)[\s./#:-]*[A-Z0-9][A-Z0-9/-]{2,}", re.I)
ENOUGH = 10  # Fewer vouchers than this never settle a practice.


@dataclass(frozen=True)
class Finding:
    probe: str
    value: dict | None
    evidence: dict
    question: dict | None = None
    guids: tuple = ()


def _groups(rows):
    return {row["name_key"]: row["parent"] for row in rows if row["type"] == "GROUP"}


def _under(parent, wanted, groups):
    """Is this parent group, or any group above it, one of `wanted`?"""
    wanted = {group.casefold() for group in wanted}
    for _ in range(50):
        if not parent:
            return False
        if parent.casefold() in wanted:
            return True
        parent = groups.get(mirror.normalized(parent))
    return False


def _question(prompt, *options):
    return {"prompt": prompt, "options": [{"value": value, "label": label} for value, label in options]}


def receipt_notes(families, purchases, **_):
    notes = sum(1 for v in families.values() if v == "receipt note")
    if notes:
        return Finding("receipt_notes", {"in_use": True}, {"receipt_notes": notes})
    if len(purchases) >= ENOUGH:
        return Finding("receipt_notes", {"in_use": False}, {"receipt_notes": 0, "purchases": len(purchases)})
    return Finding("receipt_notes", None, {"purchases": len(purchases)}, _question(
        "Does this company record goods received as Receipt Notes in Tally before the purchase?",
        ("yes", "Yes, Receipt Notes"), ("no", "No, purchases only")))


def receipt_register(purchases, **_):
    marked = sum(1 for v in purchases if RECEIPT_REGISTER.search(f"{v['narration']} {v['reference']}"))
    share = marked / len(purchases) if purchases else 0
    evidence = {"purchases": len(purchases), "with_register_number": marked}
    if len(purchases) >= ENOUGH and share >= 0.8:
        return Finding("receipt_register", {"recorded_in": "narration"}, evidence)
    if len(purchases) >= ENOUGH and share <= 0.05:
        return Finding("receipt_register", {"recorded_in": None}, evidence)
    return Finding("receipt_register", None, evidence, _question(
        "Bills carry a receipt-register (DMR) stamp. Where does this company record that number in Tally?",
        ("narration", "In the purchase narration"), ("none", "It is not recorded in Tally")))


def invoice_number_field(purchases, **_):
    referenced = sum(1 for v in purchases if v["reference"])
    narrated = sum(1 for v in purchases if not v["reference"] and INVOICE_TOKEN.search(v["narration"]))
    evidence = {"purchases": len(purchases), "reference": referenced, "narration_only": narrated}
    if len(purchases) >= ENOUGH and referenced / len(purchases) >= 0.8:
        return Finding("invoice_number_field", {"fields": ["REFERENCE"]}, evidence)
    if len(purchases) >= ENOUGH and narrated / len(purchases) >= 0.8:
        return Finding("invoice_number_field", {"fields": ["NARRATION"]}, evidence)
    return Finding("invoice_number_field", None, evidence, _question(
        "Where does this company type the supplier's invoice number on purchase vouchers?",
        ("REFERENCE", "In Supplier Invoice No. (reference)"), ("NARRATION", "In the narration")))


def bank_payments(payments, ledgers, groups, **_):
    banks = {row["name"] for row in ledgers if _under(row["parent"], ["Bank Accounts"], groups)}
    parties = {row["name"] for row in ledgers if _under(row["parent"], ["Sundry Creditors", "Sundry Debtors"], groups)}
    counters, to_parties, with_centres = Counter(), 0, 0
    considered = 0
    for voucher in payments:
        names = set(voucher["ledgers"])
        if not names & banks:
            continue
        considered += 1
        others = names - banks
        counters.update(others)
        to_parties += bool(others & parties)
        with_centres += "CATEGORYALLOCATIONS.LIST" in str(voucher["data"])
    evidence = {"bank_payments": considered, "to_party_ledgers": to_parties, "with_cost_centres": with_centres,
                "distinct_counter_ledgers": len(counters)}
    if considered >= ENOUGH and to_parties / considered >= 0.8:
        return Finding("bank_payments", {"style": "party_ledgers"}, evidence)
    top = counters.most_common(1)
    if considered >= ENOUGH and top and top[0][1] / considered >= 0.8 and with_centres / considered >= 0.5:
        ledger = next(row for row in ledgers if row["name"] == top[0][0])
        return Finding("bank_payments", {"style": "one_ledger_cost_centres", "ledger_guid": ledger["guid"],
                                         "ledger": ledger["name"]}, evidence, guids=(ledger["guid"],))
    return Finding("bank_payments", None, evidence, _question(
        "How does this company book payments made from the bank?",
        ("party_ledgers", "To each payee's own ledger"),
        ("one_ledger_cost_centres", "To one ledger, split by cost centre")))


def billwise(ledgers, groups, purchases, **_):
    suppliers = [row for row in ledgers if _under(row["parent"], ["Sundry Creditors"], groups)]
    on = [row for row in suppliers if str(row["data"].get("ISBILLWISEON", "")).casefold() == "yes"]
    evidence = {"suppliers": len(suppliers), "bill_by_bill": len(on)}
    if not suppliers:
        return None
    return Finding("billwise", {"in_use": bool(on), "share": round(len(on) / len(suppliers), 2)}, evidence)


PROBES = (receipt_notes, receipt_register, invoice_number_field, bank_payments, billwise)


def findings(connection, company, version):
    """Every probe's finding for one company at one mirror version."""
    rows = mirror.masters(connection, company["id"], version)
    types = [row["data"] for row in rows if row["type"] == "VOUCHERTYPE"]
    bases = {name: str(base or "").casefold() for name, base in base_types(types).items()}
    vouchers = [v for v in mirror.vouchers(connection, company["id"], version) if not v["cancelled"] and not v["optional"]]
    families = {v["guid"]: bases.get(v["voucher_type"].casefold(), "") for v in vouchers}
    facts = {"families": families, "groups": _groups(rows), "ledgers": [r for r in rows if r["type"] == "LEDGER"],
             "purchases": [v for v in vouchers if families[v["guid"]] == "purchase"],
             "payments": [v for v in vouchers if families[v["guid"]] == "payment"]}
    return [found for probe in PROBES if (found := probe(**facts))]


def probe(connection, company, version, job):
    """Record what the mirror settles and ask once about what it cannot."""
    if company["status"] != "authorised":
        return []
    results = findings(connection, company, version["version"])
    for found in results:
        evidence = {"kind": "probe", "version": version["version"], **found.evidence}
        if found.value is not None:
            memory.record(connection, tenant_id=company["tenant_id"], client_id=company["client_id"],
                          company_id=company["id"], kind="practice", subject=found.probe, value=found.value,
                          evidence=evidence, guids=found.guids, status="confirmed")
            continue
        if memory.live(connection, company["tenant_id"], company["client_id"], company_id=company["id"],
                       kind="practice", subject=found.probe):
            continue  # Already settled by a person's answer or earlier evidence.
        ask(connection, company, job, found)
    return results


def ask(connection, company, job, found):
    """One open question per company and probe, as a one-click Attention card."""
    question = connection.execute(
        """INSERT INTO practice_questions(tenant_id,client_id,company_id,employee_key,probe,prompt,options,evidence)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,company_id,probe) WHERE status='open'
           DO NOTHING RETURNING *""",
        (company["tenant_id"], company["client_id"], company["id"], memory.EMPLOYEE, found.probe,
         found.question["prompt"], Jsonb(found.question["options"]), Jsonb(found.evidence))).fetchone()
    if question is None:
        return None
    task = {"tenant_id": company["tenant_id"], "task_id": job["task_id"]}
    item = attention.record(connection, task, f"practice:{question['id']}", company["name"][:200], "Practice question",
                            kind="practice", target={"question_id": str(question["id"]), "company_id": str(company["id"]),
                                                     "prompt": question["prompt"], "options": question["options"]})
    connection.execute("UPDATE practice_questions SET attention_item_id=%s WHERE id=%s", (item["id"], question["id"]))
    return question
