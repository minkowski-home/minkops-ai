"""Deterministic practice probes over the mirror, and one-click practice questions.

After every published sync the probes ask how this company keeps its books:
are Receipt Notes or purchase orders in use, do purchase narrations carry
receipt-register numbers, where is the supplier's invoice number recorded, are
bank payments booked to each party's ledger or to one ledger with cost centres,
is bill-wise tracking on, does GST go to the ledgers Tally sets up as GST duties,
is a printed discount booked net or to a discount ledger. A probe that settles the question records a
confirmed structured entry, a fact about the books with the counts behind it.
An inconclusive probe raises one one-click question per company, and the
chosen option becomes the entry. No question ever blocks a run: only the items
that depend on it wait, and answering releases them.
"""

import re
from collections import Counter
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from minkops_platform import attention
from minkops_platform.errors import ServiceError

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


# Each question a probe may ask: its prompt, and each answer's label and the practice it records.
QUESTIONS = {
    "receipt_notes": ("Does this company record goods received as Receipt Notes in Tally before the purchase?", (
        ("yes", "Yes, Receipt Notes", {"in_use": True}), ("no", "No, purchases only", {"in_use": False}))),
    "purchase_orders": ("Does this company record purchase orders in Tally before the purchase?", (
        ("yes", "Yes, purchase orders", {"in_use": True}), ("no", "No, purchases only", {"in_use": False}))),
    "receipt_register": (
        "Bills carry a receipt-register (DMR) stamp. Where does this company record that number in Tally?", (
            ("narration", "In the purchase narration", {"recorded_in": "narration"}),
            ("none", "It is not recorded in Tally", {"recorded_in": None}))),
    "invoice_number_field": ("Where does this company type the supplier's invoice number on purchase vouchers?", (
        ("REFERENCE", "In Supplier Invoice No. (reference)", {"fields": ["REFERENCE"]}),
        ("NARRATION", "In the narration", {"fields": ["NARRATION"]}))),
    "bank_payments": ("How does this company book payments made from the bank?", (
        ("party_ledgers", "To each payee's own ledger", {"style": "party_ledgers"}),
        ("one_ledger_cost_centres", "To one ledger, split by cost centre", {"style": "one_ledger_cost_centres"}))),
    "gst_ledgers": (
        "This company has ledgers set up as GST duties in Tally, and others named for GST that its purchases have "
        "used. Which should new bills post GST to?", (
            ("gst_duty", "The ledgers set up as GST duties", {"use": "gst_duty"}),
            ("history", "The ledgers each supplier's earlier bills used", {"use": "history"}))),
    "discounts": ("A bill prints a trade discount. How does this company book it in Tally?", (
        ("net", "Net: each line at its discounted value", {"booked": "net"}),
        ("separately", "To a discount ledger", {"booked": "separately"}))),
}


# The workflow whose entries each question's answer changes. Its card reaches the members who run that workflow,
# and every admin (attention.py); the answer itself serves the whole desk.
SERVES = {"receipt_notes": "bill-entry", "purchase_orders": "bill-entry", "receipt_register": "bill-entry",
          "invoice_number_field": "bill-entry", "gst_ledgers": "bill-entry", "discounts": "bill-entry",
          "bank_payments": "statement-entry"}


def _question(probe):
    prompt, options = QUESTIONS[probe]
    return {"prompt": prompt, "options": [{"value": value, "label": label} for value, label, _ in options]}


def receipt_notes(families, purchases, **_):
    notes = sum(1 for v in families.values() if v == "receipt note")
    if notes:
        return Finding("receipt_notes", {"in_use": True}, {"receipt_notes": notes})
    if len(purchases) >= ENOUGH:
        return Finding("receipt_notes", {"in_use": False}, {"receipt_notes": 0, "purchases": len(purchases)})
    return Finding("receipt_notes", None, {"purchases": len(purchases)}, _question("receipt_notes"))


def purchase_orders(families, purchases, **_):
    orders = sum(1 for v in families.values() if v == "purchase order")
    if orders:
        return Finding("purchase_orders", {"in_use": True}, {"purchase_orders": orders})
    if len(purchases) >= ENOUGH:
        return Finding("purchase_orders", {"in_use": False}, {"purchase_orders": 0, "purchases": len(purchases)})
    return Finding("purchase_orders", None, {"purchases": len(purchases)}, _question("purchase_orders"))


def receipt_register(purchases, **_):
    marked = sum(1 for v in purchases if RECEIPT_REGISTER.search(f"{v['narration']} {v['reference']}"))
    share = marked / len(purchases) if purchases else 0
    evidence = {"purchases": len(purchases), "with_register_number": marked}
    if len(purchases) >= ENOUGH and share >= 0.8:
        return Finding("receipt_register", {"recorded_in": "narration"}, evidence)
    if len(purchases) >= ENOUGH and share <= 0.05:
        return Finding("receipt_register", {"recorded_in": None}, evidence)
    return Finding("receipt_register", None, evidence, _question("receipt_register"))


def invoice_number_field(purchases, **_):
    referenced = sum(1 for v in purchases if v["reference"])
    narrated = sum(1 for v in purchases if not v["reference"] and INVOICE_TOKEN.search(v["narration"]))
    evidence = {"purchases": len(purchases), "reference": referenced, "narration_only": narrated}
    if len(purchases) >= ENOUGH and referenced / len(purchases) >= 0.8:
        return Finding("invoice_number_field", {"fields": ["REFERENCE"]}, evidence)
    if len(purchases) >= ENOUGH and narrated / len(purchases) >= 0.8:
        return Finding("invoice_number_field", {"fields": ["NARRATION"]}, evidence)
    return Finding("invoice_number_field", None, evidence, _question("invoice_number_field"))


def bank_payments(payments, ledgers, groups, **_):
    """Whether bank payments go to each party's own ledger, or to one ledger split by cost centre; for the former, the
    groups its payees' ledgers sit under, most used first, which a new payee's ledger is offered under."""
    banks = {row["name"] for row in ledgers if mirror.under(row["parent"], ["Bank Accounts"], groups)}
    parties = {row["name"] for row in ledgers if mirror.under(row["parent"], ["Sundry Creditors", "Sundry Debtors"], groups)}
    parents = {row["name"]: row["parent"] for row in ledgers}
    counters, under, to_parties, with_centres = Counter(), Counter(), 0, 0
    considered = 0
    for voucher in payments:
        names = set(voucher["ledgers"])
        if not names & banks:
            continue
        considered += 1
        others = names - banks
        counters.update(others)
        under.update(parents[name] for name in others if parents.get(name))
        to_parties += bool(others & parties)
        with_centres += "CATEGORYALLOCATIONS.LIST" in str(voucher["data"])
    evidence = {"bank_payments": considered, "to_party_ledgers": to_parties, "with_cost_centres": with_centres,
                "distinct_counter_ledgers": len(counters)}
    if considered >= ENOUGH and to_parties / considered >= 0.8:
        total = sum(under.values())
        return Finding("bank_payments", {"style": "party_ledgers", "groups": [
            {"group": group, "share": round(n / total, 2)} for group, n in under.most_common(10)]}, evidence)
    top = counters.most_common(1)
    if considered >= ENOUGH and top and top[0][1] / considered >= 0.8 and with_centres / considered >= 0.5:
        ledger = next(row for row in ledgers if row["name"] == top[0][0])
        return Finding("bank_payments", {"style": "one_ledger_cost_centres", "ledger_guid": ledger["guid"],
                                         "ledger": ledger["name"]}, evidence, guids=(ledger["guid"],))
    return Finding("bank_payments", None, evidence, _question("bank_payments"))


def billwise(ledgers, groups, purchases, **_):
    suppliers = [row for row in ledgers if mirror.under(row["parent"], ["Sundry Creditors"], groups)]
    on = [row for row in suppliers if str(row["data"].get("ISBILLWISEON", "")).casefold() == "yes"]
    evidence = {"suppliers": len(suppliers), "bill_by_bill": len(on)}
    if not suppliers:
        return None
    return Finding("billwise", {"in_use": bool(on), "share": round(len(on) / len(suppliers), 2)}, evidence)


GST_WORDS = {"cgst", "sgst", "utgst", "igst", "cess"}


def gst_ledgers(ledgers, groups, purchases, **_):
    """Whether purchases post GST to the ledgers Tally sets up as GST duties, which its returns read, or to others
    named for the tax. Books with only one kind settle it; books with both ask, unless they always use the duty
    ledgers."""
    taxes = [row for row in ledgers if mirror.under(row["parent"], ["Duties & Taxes"], groups)]
    duty = {row["name"] for row in taxes if str(row["data"].get("TAXTYPE", "")).casefold() == "gst"}
    named = {row["name"] for row in taxes if row["name"] not in duty and GST_WORDS & set(mirror.words(row["name"]))}
    if not duty and not named:
        return None
    to_duty = sum(1 for v in purchases if duty & set(v["ledgers"]))
    to_named = sum(1 for v in purchases if named & set(v["ledgers"]))
    evidence = {"duty_ledgers": len(duty), "named_ledgers": len(named), "purchases_to_duty": to_duty,
                "purchases_to_named": to_named}
    if not named or (to_duty >= ENOUGH and not to_named):
        return Finding("gst_ledgers", {"use": "gst_duty"}, evidence)
    if not duty:
        return Finding("gst_ledgers", {"use": "history"}, evidence)
    return Finding("gst_ledgers", None, evidence, _question("gst_ledgers"))


# Where a discount a supplier gives is booked; a Discount Allowed ledger under expenses is the sales side.
DISCOUNT_GROUPS = ("Indirect Incomes", "Direct Incomes", "Purchase Accounts")


def discounts(ledgers, groups, purchases, **_):
    """Whether a printed discount is booked net or to a discount ledger: a company without one books net."""
    named = {row["name"]: row for row in ledgers
             if "discount" in mirror.words(row["name"]) and mirror.under(row["parent"], DISCOUNT_GROUPS, groups)}
    used = Counter(name for v in purchases for name in v["ledgers"] if name in named)
    evidence = {"discount_ledgers": len(named), "purchases_with_discount": sum(used.values())}
    if not named:
        return Finding("discounts", {"booked": "net"}, evidence)
    if used:
        ledger = named[used.most_common(1)[0][0]]
        return Finding("discounts", {"booked": "separately", "ledger_guid": ledger["guid"], "ledger": ledger["name"]},
                       evidence, guids=(ledger["guid"],))
    return Finding("discounts", None, evidence, _question("discounts"))


# Practices the voucher gate enforces once settled (vouchers.check), and a bill waits on while their question is open.
ENFORCED = ("gst_ledgers", "discounts")


def is_open(connection, company, probe):
    """Whether a question about this practice waits for the company's answer."""
    return connection.execute("SELECT 1 FROM practice_questions WHERE tenant_id=%s AND company_id=%s AND probe=%s "
                              "AND status='open'", (company["tenant_id"], company["id"], probe)).fetchone() is not None


PROBES = (receipt_notes, purchase_orders, receipt_register, invoice_number_field, bank_payments, billwise, gst_ledgers,
          discounts)
NAMES = tuple(probe.__name__ for probe in PROBES)


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
    """Record what the mirror settles and ask once about what it cannot.

    The version remembers which probes ran on it, so a probe added later still
    meets books that have not changed since (unprobed). Bills waiting on a
    practice the books now settle are checked again, as after an answer.
    """
    if company["status"] != "authorised":
        return []
    results = findings(connection, company, version["version"])
    settled = []
    for found in results:
        evidence = {"kind": "probe", "version": version["version"], **found.evidence}
        if found.value is not None:
            memory.record(connection, tenant_id=company["tenant_id"], client_id=company["client_id"],
                          company_id=company["id"], kind="practice", subject=found.probe, value=found.value,
                          evidence=evidence, guids=found.guids, status="confirmed")
            settled.append(found.probe)
            continue
        if memory.live(connection, company["tenant_id"], company["client_id"], company_id=company["id"],
                       kind="practice", subject=found.probe):
            continue  # Already settled by a person's answer or earlier evidence.
        ask(connection, company, job, found)
    connection.execute("UPDATE mirror_versions SET stats = stats || %s WHERE company_id=%s AND version=%s",
                       (Jsonb({"probed": list(NAMES)}), company["id"], version["version"]))
    from .bill_entry import practice_settled
    for name in settled:
        practice_settled(connection, company["tenant_id"], company["id"], name)
    return results


def unprobed(version):
    """Whether a published version has not met every probe: one added since its books last changed."""
    return bool(set(NAMES) - set((version["stats"] or {}).get("probed") or ()))


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
                                                     "prompt": question["prompt"], "options": question["options"],
                                                     "workflows": [SERVES[found.probe]]})
    connection.execute("UPDATE practice_questions SET attention_item_id=%s WHERE id=%s", (item["id"], question["id"]))
    return question


def settled(connection, company, probe):
    """What this company's books, or a person's answer, settled for a probe; None while it is open.

    A year-split sibling's practice holds for the company as a whole.
    """
    parts = [row["id"] for row in connection.execute(
        "SELECT id FROM companies WHERE tenant_id=%s AND client_id=%s AND guid=%s",
        (company["tenant_id"], company["client_id"], company["guid"]))]
    rows = memory.entries(connection, company["tenant_id"], company["client_id"], company_ids=parts,
                          kinds=["practice"], subjects=[probe], statuses=("confirmed",))
    own = [row for row in rows if row["company_id"] == company["id"]]
    return (own or rows or [{"value": None}])[0]["value"]


def question(target):
    """The card a person answers: its prompt and the offered answers."""
    return {"prompt": target["prompt"],
            "options": [{"action": option["value"], "label": option["label"]} for option in target["options"]]}


def decide(connection, tenant, user, item, action):
    """Answer a practice card: the answer becomes the company's confirmed practice, and the bills that waited on
    it are checked again."""
    question_row = connection.execute("SELECT * FROM practice_questions WHERE tenant_id=%s AND id=%s FOR UPDATE",
                                      (tenant["id"], item["target"]["question_id"])).fetchone()
    if question_row is None or question_row["status"] != "open":
        raise ServiceError("conflict", "This question is no longer open.")
    answers = {value: (label, entry) for value, label, entry in QUESTIONS.get(question_row["probe"], ("", ()))[1]}
    if action not in answers:
        raise ServiceError("invalid", "Choose one of the offered answers.")
    label, entry = answers[action]
    memory.record(connection, tenant_id=tenant["id"], client_id=question_row["client_id"],
                  company_id=question_row["company_id"], kind="practice", subject=question_row["probe"], value=entry,
                  evidence={"kind": "answer", "question": str(question_row["id"]), "answer": action},
                  status="confirmed", actor_id=user["id"], overrule_answers=True)
    connection.execute("UPDATE practice_questions SET status='answered',answer=%s,answered_by=%s,answered_at=now() "
                       "WHERE id=%s", (Jsonb({"value": action}), user["id"], question_row["id"]))
    attention.audit(connection, item, user["id"], "answered", f"Answered: {label}.")
    connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                       (user["id"], item["id"]))
    # Bills hold only while their company's practice is open; imported here, as bill entry reads this module.
    from .bill_entry import practice_settled
    practice_settled(connection, tenant["id"], question_row["company_id"], question_row["probe"])
    return {"status": "answered"}
