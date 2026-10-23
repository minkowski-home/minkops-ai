# Synthetic look-alikes

Invented copies of the structures PR Infra's sample files exhibit, for tests
and benchmarks that must run anywhere. Every name, number, GSTIN, account and
amount is made up. Expected answers sit beside the inputs; they are for scorers
only and must never enter a model's input.

| File | Reproduces |
| --- | --- |
| `statements/icici-detailed-statement-sep-2026.xlsx` | The bank's "Detailed Statement": metadata rows with a non-filtering "Transaction type: DR" label, header on row 17, values as text in Indian digit grouping, three date formats, the narration families with their measured counts (700 INF/NEFT, 208 UPI, 130 RTGS, 106 MMT/IMPS, 55 INF/INFT, 6 BIL/ONL, 19 other), 8 NEFT returns that carry their payment's UTR on the same day, 881 payees across 1,203 debits, one repeated bank transaction ID, site codes and a repeated batch reference in the remarks, and footer controls that prove the month. |
| `bills/2901 …15.3.26.pdf` | An image-only, two-page e-invoice whose Amount column includes GST, so quantity × rate rebuilds the printed taxable value but the column does not. |
| `bills/2916 …6.3.26.pdf` | An inter-state e-invoice with a goods line and a services (handling) line. |

Both bills:
- carry a signed QR shaped like an IRP payload, an e-way bill page, a receipt-register (DMR) stamp, a signature and a handwritten site note;
- are addressed to a buyer registration in a different state from the one tied to the bank account.

`irp-test-public-key.pem` verifies their QR signatures; the signing key was thrown away.

Regenerate with the dev dependency group:

```bash
uv run --all-packages python scripts/synthetic_fixtures.py statement packages/fixtures/synthetic/statements/icici-detailed-statement-sep-2026.xlsx
```

```bash
uv run --all-packages python scripts/synthetic_fixtures.py bills packages/fixtures/synthetic/bills
```

The real files stay in the private fixture store, `~/minkops-private/fixtures/pr-infra/` (owner-only, never in git). `scripts/tests/test_synthetic_fixtures.py` checks the look-alikes everywhere and the real files' structure where the store exists; set `MINKOPS_PRIVATE_FIXTURES` to use another location.
