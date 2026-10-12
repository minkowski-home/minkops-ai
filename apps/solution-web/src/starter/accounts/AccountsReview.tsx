import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { CatalogReview } from "./CatalogReview";
import { DiscoveryReview } from "./Discovery";
import { applyLocalPlan, applyTallyPlan } from "./localFiles";
import type { BillResult, Catalog, Run } from "./types";
import { LoadingIndicator, RetryMessage, Spinner } from "../components/Feedback";
import { TaskProgress } from "../workspace/TaskProgress";
import { progressView } from "../workspace/progress";

/** Decisions only. Accounting edits and corrections belong in original tools. */
function RunReview({ tenant, taskId, controlState = "active" }: { tenant: string; taskId: string; controlState?: string }) {
  const { user } = useAuth();
  const { workspaceId } = useParams();
  const [run, setRun] = useState<Run | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const applying = useRef(false),
    attempted = useRef("");
  const base = `/api/tenants/${tenant}/accounts`;
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await api<Run | null>(`${base}/tasks/${taskId}/run`);
        if (!active) return;
        setRun(value); setLoaded(true); setLoadError("");
        setCatalog((current) => current ?? (value?.result as Catalog | null));
        if (value && !["completed", "failed"].includes(value.state))
          timer = setTimeout(() => void poll(), 2000);
      } catch {
        if (active) { setLoadError("Could not refresh task. Retrying automatically."); timer = setTimeout(() => void poll(), 5000); }
      }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [base, taskId, attempt, controlState]);
  async function apply(value: Run) {
    if (!user || value.actor_id !== user.id || applying.current || controlState !== "active" || loadError) return;
    applying.current = true;
    setBusy(true);
    setError("");
    try {
      for (const write of value.writes.filter(w => !w.verified_at && !w.cancelled_at)) {
        const current = await api<Run>(`${base}/runs/${value.id}`);
        if (current.state !== "writing") break;
        try { await applyLocalPlan(tenant, value.id, write, user.csrf_token, typeof value.config.destination_device_id === "string" ? value.config.destination_device_id : undefined); }
        catch { setError("Save needs attention"); }
      }
      for (const w of (value.tally_writes ?? []).filter(
        (w) => !w.finished_at && !w.cancelled_at
      )) {
        // Reload the control intent between saves. A save in flight retains its
        // receipt; pausing never starts the next bill in a stale client loop.
        const current = await api<Run>(`${base}/runs/${value.id}`);
        if (current.state !== "writing") break;
        await applyTallyPlan(tenant, value.id, w, user.csrf_token);
      }
      setRun(await api<Run>(`${base}/runs/${value.id}`));
    } catch {
      setError("Save needs attention");
    } finally {
      applying.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    // Resume is an explicit operator request to retry remaining immutable plans.
    if (controlState !== "active") attempted.current = "";
    const key = run
      ? [
          ...run.writes.filter((w) => !w.verified_at && !w.cancelled_at).map((w) => w.id),
          ...(run.tally_writes ?? [])
            .filter((w) => !w.finished_at && !w.cancelled_at)
            .map((w) => w.id)
        ].join(":")
      : "";
    if (
      run?.state === "writing" &&
      controlState === "active" && !loadError &&
      key &&
      key !== attempted.current &&
      !applying.current
    ) {
      attempted.current = key;
      void apply(run);
    }
    // Each immutable write gets one attempt; retries remain explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, controlState, loadError]);
  async function act(path: string, body: unknown) {
    if (!user || controlState !== "active" || loadError) return;
    setBusy(true);
    setError("");
    try {
      setRun(
        await api<Run>(
          path,
          { method: "POST", body: JSON.stringify(body) },
          user.csrf_token
        )
      );
    } catch {
      setError("Action unavailable. Use Do nothing.");
    } finally {
      setBusy(false);
    }
  }
  if (!run) return loadError ? <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{loadError}</RetryMessage>
    : loaded ? null : <LoadingIndicator>Loading workflow results…</LoadingIndicator>;
  const discovery = run.workflow_key === "source-discovery";
  const ownsRun = run.actor_id === user?.id;
  const result = run.result as BillResult | null;
  const provenance = run.config.file_provenance as { id: string; path: string }[];
  const name = (id: string) => provenance?.find((f) => f.id === id)?.path ?? id;
  const records = result?.records ?? [];
  const unmatched = (result?.unresolved ?? []).filter(
    (i) => !records.some((r) => r.source_file_id === i.source_file_id)
  );
  return (
    <section className="accounts-panel" aria-label="Workflow result">
      {discovery && <TaskProgress view={progressView({
        status: controlState !== "active" ? controlState : run.state === "review" ? "attention" : run.state === "completed" ? "completed" : run.state === "failed" ? "failed" : "running",
        progress: 0, events: [{ event_type: run.state }],
      }, "source-discovery")} stale={Boolean(loadError)} />}
      {loadError && <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{loadError}</RetryMessage>}
      {busy && <p className="loading-feedback" role="status"><Spinner />Working…</p>}
      <h3>{discovery ? "Source discovery" : "Bill entry"}</h3>
      <Link to={`/${workspaceId ?? tenant}/attention`}>Attention items</Link>
      {["queued", "executing", "collecting"].includes(run.state) && (
        <p role="status">Working…</p>
      )}
      {run.state === "failed" && <p role="alert">Needs attention</p>}
      {discovery && run.state === "review" && catalog && (
        <>
          <CatalogReview
            catalog={catalog}
            provenance={provenance}
            filter=""
            onChange={setCatalog}
          />
          <button
            className="button button-ghost"
            disabled={busy || controlState !== "active" || Boolean(loadError)}
            onClick={() =>
              void act(`${base}/runs/${run.id}/approve`, { result: catalog })
            }
          >
            Confirm mappings
          </button>
        </>
      )}
      {!discovery &&
        records.map((r, index) => {
          const pending = !["saved", "duplicate", "rejected", "writing"].includes(
            r.status ?? ""
          );
          const needsAttention = Boolean(
            r.findings.length ||
            result?.unresolved?.some((i) => i.source_file_id === r.source_file_id)
          );
          const missingSupplier = (!r.master_refs || r.master_refs.vendor?.new_supplier === true) && r.findings.some((f) =>
            f.includes("missing from the confirmed Tally ledgers")
          );
          const decide = (action: string) =>
            act(`/api/tenants/${tenant}/attention/bills/${run.id}/${r.source_file_id}`, {
              action
            });
          return (
            <article className="accounts-bill" key={`${r.source_file_id}:${index}`}>
              <h4>{name(r.source_file_id)}</h4>
              <p>
                {r.company_name ?? r.sheet} ·{" "}
                {String(r.data.invoice_number ?? r.data["Invoice Number"] ?? "")} ·{" "}
                {String(r.data.total ?? r.data.Total ?? "")}
              </p>
              <a
                href={`${base}/files/${r.source_file_id}/content`}
                target="_blank"
                rel="noreferrer"
              >
                View bill
              </a>
              {Boolean(r.tax_allocations?.length) && <p className="muted">Tax: {r.tax_allocations!.map(line =>
                `${line.ledger ?? "Pending ledger"} · ${new Intl.NumberFormat("en-IN").format(line.amount)}`).join(" · ")}</p>}
              <span role="status">
                {" "}
                {missingSupplier
                  ? "Missing supplier"
                  : needsAttention
                    ? "Needs review"
                    : (r.status ?? "Ready")}
              </span>
              {pending && run.state === "review" && ownsRun && (
                <div className="accounts-toolbar">
                  {!missingSupplier && (
                    <button
                      className="button button-ghost"
                      disabled={busy || controlState !== "active" || Boolean(loadError)}
                      onClick={() => void decide("guess")}
                    >
                      {needsAttention ? "Best guess write" : "Write bill"}
                    </button>
                  )}
                  {missingSupplier && r.data.tax === 0 && (
                    <button
                      className="button button-ghost"
                      disabled={busy || controlState !== "active" || Boolean(loadError)}
                      onClick={() => void decide("supplier")}
                    >
                      Create this ledger
                    </button>
                  )}
                  <button
                    className="button button-ghost"
                    disabled={busy || controlState !== "active" || Boolean(loadError)}
                    onClick={() => void decide("nothing")}
                  >
                    Do nothing
                  </button>
                  {result?.unresolved?.some(
                    (i) => i.source_file_id === r.source_file_id
                  ) && (
                    <button
                      className="button button-ghost"
                      disabled={busy || controlState !== "active" || Boolean(loadError)}
                      onClick={() => void decide("retry")}
                    >
                      Recheck bill
                    </button>
                  )}
                </div>
              )}
            </article>
          );
        })}
      {!discovery &&
        unmatched.map((i) => (
          <article className="accounts-bill" key={i.source_file_id}>
            <h4>{name(i.source_file_id)}</h4>
            <p>Needs attention</p>
            <button
              className="button button-ghost"
              disabled={busy || !ownsRun || controlState !== "active" || Boolean(loadError)}
              onClick={() =>
                void act(
                  `/api/tenants/${tenant}/attention/bills/${run.id}/${i.source_file_id}`,
                  { action: "nothing" }
                )
              }
            >
              Do nothing
            </button>
            <button
              className="button button-ghost"
              disabled={busy || !ownsRun || controlState !== "active" || Boolean(loadError)}
              onClick={() =>
                void act(
                  `/api/tenants/${tenant}/attention/bills/${run.id}/${i.source_file_id}`,
                  { action: "retry" }
                )
              }
            >
              Recheck bill
            </button>
          </article>
        ))}
      {!discovery &&
        ownsRun &&
        run.state === "review" &&
        records.some(
          (r) =>
            r.decision === "approve" &&
            !r.findings.length &&
            !["saved", "duplicate", "rejected", "writing"].includes(r.status ?? "") &&
            !result?.unresolved?.some((i) => i.source_file_id === r.source_file_id)
        ) && (
          <button
            className="button button-ghost"
            disabled={busy || controlState !== "active" || Boolean(loadError)}
            onClick={() =>
              void act(`${base}/runs/${run.id}/approve`, {
                result: {
                  ...result,
                  records: records.map((r) => ({
                    ...r,
                    decision:
                      r.findings.length ||
                      result?.unresolved?.some(
                        (i) => i.source_file_id === r.source_file_id
                      )
                        ? "hold"
                        : r.decision
                  }))
                },
                acknowledge_findings: true
              })
            }
          >
            Write ready bills
          </button>
        )}
      {run.state === "writing" && ownsRun && (
        <button
          className="button button-ghost"
          disabled={busy || controlState !== "active" || Boolean(loadError)}
          onClick={() => void apply(run)}
        >
          Resume saves
        </button>
      )}
      {run.state === "completed" && <p role="status">Finished</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

export function AccountsReview({ tenant, taskId, controlState = "active" }: { tenant: string; taskId: string; controlState?: string }) {
  const [native, setNative] = useState<boolean | null>(null),
    [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    void api<unknown>(`/api/tenants/${tenant}/discovery/tasks/${taskId}`)
      .then((r) => {
        if (active) setNative(Boolean(r));
      })
      .catch(() => {
        if (active) setError("Could not load task");
      });
    return () => {
      active = false;
    };
  }, [tenant, taskId, attempt]);
  if (error) return <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{error}</RetryMessage>;
  if (native === null) return <LoadingIndicator>Loading workflow…</LoadingIndicator>;
  return native ? (
    <DiscoveryReview tenant={tenant} taskId={taskId} controlState={controlState} />
  ) : (
    <RunReview tenant={tenant} taskId={taskId} controlState={controlState} />
  );
}
