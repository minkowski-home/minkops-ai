"""The hold-code to actions matrix is closed, server-owned and changes only on purpose.

The golden table below is written out independently of holds.py: adding a code
or widening an action must update both, in review.
"""

import unittest

from minkops_platform.accounts import holds

BILL, STATEMENT, BOTH = {"bill"}, {"statement"}, {"bill", "statement"}
GOLDEN = {
    ("nothing", "retry"): (BILL, [
        "not_a_bill", "multiple_bills_unclear", "required_value_missing", "source_values_conflict",
        "supplier_unresolved", "date_before_books", "identity_rule_unknown", "date_outside_company_period",
        "destination_changed", "voucher_type_unresolved", "extraction_failed", "human_review"]),
    ("guess", "nothing", "retry"): (BILL, ["source_unreadable", "posting_profile_miss", "manual_review"]),
    ("supplier", "nothing", "retry"): (BILL, ["supplier_missing"]),
    ("retry_save", "nothing"): (BOTH, [
        "company_not_open", "no_company", "duplicate_company", "not_running", "port_closed", "busy", "too_many",
        "invalid_response", "rejected", "save_waiting", "save_interrupted", "pc_unavailable", "save_held"]),
    ("nothing",): (STATEMENT, [
        "statement_format", "statement_layout_unconfirmed", "statement_value", "statement_balance",
        "statement_closing", "statement_summary", "statement_formula", "statement_conflict", "possible_existing",
        "uncertain_import"]),
}
# Codes a bill and a statement row share.
SHARED = {
    "company_unresolved": ("nothing", "retry"), "unsupported_structure": ("nothing", "retry"),
    "run_stopped": ("nothing", "retry"), "classification_uncertain": ("guess", "nothing", "retry"),
}
STATEMENT_ONLY = {
    "statement_layout_unknown": ("nothing", "retry"), "statement_layout_changed": ("nothing", "retry"),
    "statement_transfer_unpaired": ("nothing", "retry"), "statement_interpretation": ("guess", "nothing", "retry"),
    "ledger_unresolved": ("guess", "nothing", "retry"), "branch_unresolved": ("guess", "nothing", "retry"),
    "statement_save_waiting": ("retry_save", "nothing"), "statement_save_held": ("retry_save", "nothing"),
}


class HoldMatrixTest(unittest.TestCase):
    def test_every_code_has_exactly_its_golden_actions_and_scope(self):
        expected = {code: (actions, scopes) for actions, (scopes, codes) in GOLDEN.items() for code in codes}
        expected.update({code: (actions, STATEMENT) for code, actions in STATEMENT_ONLY.items()})
        expected.update({code: (actions, BOTH) for code, actions in SHARED.items()})
        actual = {code: (hold.actions, set(hold.scopes)) for code, hold in holds.HOLDS.items()}
        self.assertEqual(actual, expected)

    def test_actions_are_a_closed_list_with_labels(self):
        for hold in holds.HOLDS.values():
            self.assertTrue(set(hold.actions) <= set(holds.ACTIONS), hold.code)
            self.assertIn("nothing", hold.actions, "Do nothing is always available")
        self.assertEqual(set(holds.ACTIONS), {"nothing", "retry", "guess", "supplier", "retry_save"})

    def test_an_unknown_code_fails_closed_to_actions_that_cannot_write(self):
        self.assertEqual(holds.hold("never_heard_of_it").actions, ("nothing", "retry"))
        self.assertEqual(holds.actions(["never_heard_of_it"]), ("nothing", "retry"))
        self.assertEqual(holds.actions([]), ("guess", "nothing", "retry"))  # Uncoded holds are manual review.

    def test_several_codes_keep_only_the_actions_every_code_allows(self):
        self.assertEqual(holds.actions(["supplier_missing", "classification_uncertain"]), ("nothing", "retry"))
        self.assertEqual(holds.actions(["classification_uncertain", "date_before_books"]), ("nothing", "retry"))
        self.assertEqual(holds.actions(["busy", "rejected"]), ("retry_save", "nothing"))

    def test_interpretation_holds_never_offer_retry_save(self):
        # Retrying the same plan fixes only destination problems; a reading the
        # model or a check doubted must be rechecked or decided instead.
        for hold in holds.HOLDS.values():
            if hold.kind == holds.EXCEPTION:
                self.assertNotIn("retry_save", hold.actions, hold.code)

    def test_labels_fit_attention_and_statement_reasons_name_an_entry(self):
        for hold in holds.HOLDS.values():
            self.assertTrue(1 <= len(hold.label) <= 80, hold.code)  # attention_items.label constraint.
            self.assertNotIn("bill", hold.reason_for("statement").casefold() if "statement" in hold.scopes else "",
                             hold.code)


if __name__ == "__main__":
    unittest.main()
