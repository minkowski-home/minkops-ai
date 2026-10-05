"""Opt-in paid hosted verification of exactly one native smoke mapping run."""

import os
import sys
from pathlib import Path
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from minkops_platform.accounts.run_store import AccountsRunStore
from minkops_platform.accounts.worker import process
from minkops_platform.runtime.lifecycle import work_once
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "apps/solution-api/.env")
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("OPENAI_API_KEY is not configured for the API.")
run_id = UUID(sys.argv[1])
url = os.environ["DATABASE_URL"]
with psycopg.connect(url, row_factory=dict_row) as c:
    run = c.execute(
        "SELECT * FROM account_runs WHERE id=%s AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant')",
        (run_id,),
    ).fetchone()
    if not run or run["state"] != "queued":
        raise SystemExit("Select one queued mock-client discovery run.")


class SelectedRun(AccountsRunStore):
    def candidates(self, connection):
        return connection.execute(
            "SELECT * FROM account_runs WHERE id=%s AND tenant_id=(SELECT id FROM tenants WHERE slug='mock-tenant') AND state IN ('queued','executing')",
            (run_id,),
        ).fetchall()


print("Starting the real hosted mapping workflow.", flush=True)
work_once(url, SelectedRun(), process)
with psycopg.connect(url, row_factory=dict_row) as c:
    final = c.execute("SELECT state,result FROM account_runs WHERE id=%s", (run_id,)).fetchone()
    if final["state"] != "review":
        raise SystemExit(
            "Hosted mapping did not reach review. Check the task for its recorded failure."
        )
    print({"state": final["state"], "sheets": len(final["result"]["sheets"])}, flush=True)
