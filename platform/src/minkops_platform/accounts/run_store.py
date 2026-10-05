"""Accounts persistence adapter for shared hosted-run lifecycle guarantees."""

from psycopg.types.json import Jsonb

from .repository import observe, run_for


class AccountsRunStore:
    def candidates(self, connection):
        return connection.execute("""SELECT * FROM account_runs WHERE state='queued'
            OR (state='executing' AND updated_at < now()-interval '30 seconds')
            ORDER BY updated_at LIMIT 10""").fetchall()

    def get(self, connection, tenant_id, run_id):
        return run_for(connection, tenant_id, run_id)

    def fail(self, connection, run, message):
        connection.execute(
            "UPDATE account_runs SET error=%s WHERE tenant_id=%s AND id=%s",
            (message, run["tenant_id"], run["id"]),
        )
        observe(connection, run, "failed", message, 20)

    def save_session(self, connection, run, session_id, turn_id):
        connection.execute(
            """UPDATE account_runs SET session_id=coalesce(%s,session_id),
                turn_id=coalesce(%s,turn_id),updated_at=now() WHERE tenant_id=%s AND id=%s""",
            (session_id, turn_id, run["tenant_id"], run["id"]),
        )

    def save_result(self, connection, run, result):
        connection.execute(
            "UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s",
            (Jsonb(result), run["tenant_id"], run["id"]),
        )

    def claim_cleanup(self, connection):
        run = connection.execute("""SELECT id,tenant_id,session_id FROM account_runs
            WHERE state NOT IN ('queued','executing') AND session_id IS NOT NULL
            AND NOT coalesce((config->>'hosted_session_closed')::boolean,false)
            AND coalesce((config->>'cleanup_attempt_count')::integer,0) < 10
            AND coalesce((config->>'cleanup_attempt_at')::timestamptz,'epoch') < now()-interval '1 minute'
            ORDER BY updated_at LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if run:
            connection.execute(
                """UPDATE account_runs SET config=config || jsonb_build_object('cleanup_attempt_at',now(),
                    'cleanup_attempt_count',coalesce((config->>'cleanup_attempt_count')::integer,0)+1)
                    WHERE tenant_id=%s AND id=%s""",
                (run["tenant_id"], run["id"]),
            )
        return run

    def mark_closed(self, connection, run):
        connection.execute(
            """UPDATE account_runs SET config=config || '{"hosted_session_closed":true}'::jsonb
                WHERE tenant_id=%s AND id=%s""",
            (run["tenant_id"], run["id"]),
        )
