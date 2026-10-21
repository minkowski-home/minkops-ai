"""Small durable progress facts shared by run and task presentations."""


def execution_status(connection, run, control="active"):
    rows = connection.execute("""SELECT id,state,execution_stage,awaited_profile_id,awaited_layout_run_id,
        config#>'{awaits,layouts}' AS layout_profiles,updated_at
        FROM workflow_runs WHERE tenant_id=%s AND (id=%s OR parent_run_id=%s) AND NOT superseded""",
        (run["tenant_id"], run["id"], run["id"])).fetchall()
    children = [r for r in rows if str(r["id"]) != str(run["id"])]
    bills = [r for r in children if r["execution_stage"] is None] or [r for r in rows if not children]
    ready = sum(r["state"] in ("review", "completed", "failed") for r in bills)
    active = sum(r["state"] == "executing" for r in bills)
    queued = sum(r["state"] == "queued" for r in bills)
    awaiting = {str(r[key]) for r in rows for key in ("awaited_profile_id",) if r[key]}
    layout_profiles = {str(profile) for r in rows for profile in (r["layout_profiles"] or [])}
    items = connection.execute("""SELECT id,kind,label,target FROM attention_items
        WHERE tenant_id=%s AND status='pending' AND kind IN ('profile','layout')
          AND (task_id=%s OR target->>'profile_id'=ANY(%s))
        ORDER BY created_at,id""", (run["tenant_id"], run["task_id"], list(awaiting | layout_profiles))).fetchall()
    blockers = [{"kind": item["kind"], "attention_item_id": str(item["id"]), "label": item["label"],
                 "company": item["target"].get("company"),
                 "waiting": (sum(bool(r["awaited_layout_run_id"]) or str(item["target"].get("profile_id")) in (r["layout_profiles"] or []) for r in rows) if item["kind"] == "layout" else
                             sum(str(r["awaited_profile_id"]) == str(item["target"].get("profile_id")) for r in rows))}
                for item in items if item["kind"] == "layout" or str(item["target"].get("profile_id")) in awaiting]
    stage = run["state"]
    if control != "active":
        stage = control
    elif blockers:
        stage = "awaiting_input"
    elif any(r["state"] in ("queued", "executing") and r["execution_stage"] == "triage" for r in children):
        stage = "routing"
    elif any(r["state"] in ("queued", "executing") and r["execution_stage"] == "posting_profile" for r in children):
        stage = "learning_pattern"
    elif any(r["state"] in ("queued", "executing") and r["execution_stage"] == "layout" for r in children):
        stage = "learning_layout"
    elif stage == "executing":
        stage = "reading" if active or ready else "queued"
    latest = connection.execute("""SELECT max(d.created_at) AS at FROM workflow_run_diagnostics d
        JOIN workflow_runs r ON r.tenant_id=d.tenant_id AND r.id=d.run_id
        WHERE r.tenant_id=%s AND (r.id=%s OR r.parent_run_id=%s)""",
        (run["tenant_id"], run["id"], run["id"])).fetchone()["at"]
    return {"blockers": blockers, "execution": {"stage": stage, "ready": ready, "total": len(bills) or len(run["file_ids"]),
            "active": active, "queued": queued, "last_activity_at": latest or run.get("updated_at")}}
