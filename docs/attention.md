# Attention

README's Product Vision and AGENTS.md are the canonical product rules. Accounting
edits belong in the original systems, never in Minkops.

Attention lists the events that need a person, across workflows
(`platform/src/minkops_platform/attention.py`). Items are tenant-scoped
`attention_items`, and `attention_events` keeps their audit trail: who opened,
answered, reopened or closed each one, with a short summary. A bill or statement
row that needs a decision is not an Attention item. It holds on its run record,
with the one-click actions its hold allows; see [Bill entry](bill-entry.md#review)
and [Statement entry](statement-entry.md#review-and-writes). Attention carries
what belongs to no single record:

| Item | Opened when | Closed by |
| --- | --- | --- |
| New company found | A PC's sync shows a company the tenant has not authorised (`accounts/sync.py`) | Authorising it for a client business (`POST /api/tenants/{slug}/companies/{id}/authorise`), which mirrors it |
| Statement layout question | Only a person can settle a sheet's date order, or how to read rows without a running balance (`accounts/statement_layouts.py`) | Its answer, which reads the waiting rows |
| Transactions missing | A statement opens at a different balance from where the previous one for that bank ledger closed (`accounts/statement_entry.py`) | Done, once the missing statement is entered |
| Practice question | The mirror cannot settle how the client books something, such as whether Receipt Notes are in use (`accounts/practice.py`) | Its one-click answer, which becomes the company's practice and releases the bills that waited on it |

A question card carries its prompt and the answers the server offers, each with its
label. It is answered with `POST /api/tenants/{slug}/attention/{item}/decision` and
one of those actions, once per member. The same answer sent again
returns its receipt; a different one conflicts. `GET` on the same path returns
the receipt.

Workflows restate an item by its event key whenever they settle again. Restating
changes nothing, so an operator's Done survives. A new event reopens the item with
its new reason. Any workspace member may mark an item Done
(`POST .../attention/{item}/done`). Lists are grouped by workflow, employee or
status, sorted newest first or by name, 200 per page, and show only items of the
clients a member can reach. The warehouse is future work; the audit trail lives in
PostgreSQL.
