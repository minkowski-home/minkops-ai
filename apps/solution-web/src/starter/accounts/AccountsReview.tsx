import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { downloadFile } from "../desktop/bridge";
import { useAuth } from "../contexts/AuthContext";
import { CatalogReview } from "./CatalogReview";
import { BillDetailsButton } from "./BillDetails";
import { DiscoveryReview } from "./Discovery";
import { applyLocalPlan, applyTallyPlan } from "./localFiles";
import { billActions, billOutcome, inputsWithoutProposal, isPending, missingSupplier, needsAttention, type BillAction } from "./billView";
import type { BillResult, Catalog, Run } from "./types";
import { LoadingIndicator, RetryMessage, Spinner } from "../components/Feedback";
import { TaskProgress } from "../workspace/TaskProgress";
import { progressView } from "../workspace/progress";
import {StatementReview} from './Statements';

const ACTION_LABELS: Record<BillAction, string> = {
  guess: "Best guess write",
  supplier: "Create this ledger",
  nothing: "Do nothing",
  retry: "Recheck bill",
  retry_save: "Retry save",
};

/** Decisions only. Accounting edits and corrections belong in original tools. */
function RunReview({ tenant, taskId, controlState = "active" }: { tenant: string; taskId: string; controlState?: string }) {
  const { user } = useAuth();
  const { workspaceId } = useParams();
  const [run, setRun] = useState<Run | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const bulkDialog = useRef<HTMLDialogElement>(null);
  const [bulk, setBulk] = useState<{fileId: string; proposal: number | null; action: BillAction;
    count: number; description: string; preview_token: string} | null>(null);
  useEffect(() => { if (bulk) bulkDialog.current?.showModal(); }, [bulk]);
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
      run.workflow_key !== "statement-entry" &&
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
      setError("Could not complete this action. Check the current outcome before trying again.");
    } finally {
      setBusy(false);
    }
  }
  async function previewBulk(fileId: string, proposal: number | null, action: BillAction) {
    if (!user || !run || busy || controlState !== "active" || loadError) return;
    setBusy(true); setError("");
    try {
      const preview = await api<{count: number; description: string; preview_token: string}>(
        `/api/tenants/${tenant}/attention/bills/${run.id}/${fileId}/bulk-preview`,
        {method: "POST", body: JSON.stringify({action, proposal})}, user.csrf_token);
      setBulk({...preview, fileId, proposal, action});
    } catch (error) { setError(error instanceof Error ? error.message : "Could not preview similar bills."); }
    finally { setBusy(false); }
  }
  function decisionButtons(fileId: string, proposal: number | null, actions: BillAction[], counts: Partial<Record<BillAction, number>>, attention = true) {
    return <div className="accounts-toolbar">{actions.map(action => <div key={action} className="accounts-toolbar">
      <button className="button button-ghost" disabled={busy || controlState !== "active" || Boolean(loadError)}
        onClick={() => void act(`/api/tenants/${tenant}/attention/bills/${run?.id}/${fileId}`, {action, proposal})}>
        {action === "guess" && !attention ? "Write bill" : ACTION_LABELS[action]}</button>
      {action !== "guess" && (counts[action] ?? 0) > 1 && <button className="button button-ghost"
        disabled={busy || controlState !== "active" || Boolean(loadError)}
        onClick={() => void previewBulk(fileId, proposal, action)}>
        Apply {ACTION_LABELS[action]} to all {counts[action]} similar</button>}
    </div>)}</div>;
  }
  if (!run) return loadError ? <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{loadError}</RetryMessage>
    : loaded ? null : <LoadingIndicator>Loading workflow results…</LoadingIndicator>;
  if (run.workflow_key === 'statement-entry') return <StatementReview tenant={tenant} run={run} onChanged={setRun} blocked={controlState !== 'active' || Boolean(loadError)}/>;
  const discovery = run.workflow_key === "source-discovery";
  const ownsRun = run.actor_id === user?.id;
  const result = run.result as BillResult | null;
  const provenance = run.config.file_provenance as { id: string; path: string }[];
  const name = (id: string) => provenance?.find((f) => f.id === id)?.path ?? id;
  const records = result?.records ?? [];
  const saved = run.review?.saved ?? records.filter(r => r.status === "saved").length;
  const duplicates = run.review?.duplicates ?? records.filter(r => r.status === "duplicate").length;
  const exportUnavailable = run.review?.export_unavailable ??
    (!["review", "completed", "failed", "stopped"].includes(run.state) || !result ? "Export is ready after processing and destination saves have finished." : "");
  const reason = (fileId: string, index: number | null = null) => run.review?.rows.find(
    row => row.source_file_id === fileId && row.record_index === index)?.reason ?? "This bill needs manual review in the original system.";
  const { unresolved: unmatched, deferred } = inputsWithoutProposal(result);
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
      {!discovery && <div className="accounts-toolbar">
        <button className="button button-ghost" disabled={busy || Boolean(loadError) || Boolean(exportUnavailable)}
          onClick={() => {
            setBusy(true); setError("");
            void downloadFile(`${base}/runs/${run.id}/unsaved-bills.csv`, `unsaved-bills-${run.id}.csv`)
              .catch(() => setError("Could not download the exception sheet. Please try again."))
              .finally(() => setBusy(false));
          }}>Export CSV</button>
        {exportUnavailable && <p className="muted">{exportUnavailable}</p>}
      </div>}
      {!discovery && (saved > 0 || duplicates > 0) && <details>
        <summary>{saved} saved · {duplicates} already in Tally</summary>
        <p>{records.filter(r => ["saved", "duplicate"].includes(r.status ?? "")).map(r =>
          `${name(r.source_file_id)} (${String(r.data.invoice_number ?? "")})`).join(" · ")}</p>
      </details>}
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
          if (r.status === "saved" || r.status === "duplicate") return null;
          const pending = isPending(r);
          const attention = needsAttention(r, result);
          const supplierMissing = missingSupplier(r);
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
              <BillDetailsButton record={r} config={run.config} name={name(r.source_file_id)} />
              {Boolean(r.tax_allocations?.length) && <p className="muted">Tax: {r.tax_allocations!.map(line =>
                `${line.ledger ?? "Pending ledger"} · ${new Intl.NumberFormat("en-IN").format(line.amount)}`).join(" · ")}</p>}
              <span role="status">
                {" "}
                {supplierMissing && pending ? "Missing supplier" : billOutcome(r.status, attention)}
              </span>
              <p>{reason(r.source_file_id, index)}</p>
              {pending && run.state === "review" && ownsRun && (
                decisionButtons(r.source_file_id, index, billActions(r), r.bulk_actions ?? {}, attention)
              )}
            </article>
          );
        })}
      {!discovery &&
        unmatched.map((i) => (
          <article className="accounts-bill" key={i.source_file_id}>
            <h4>{name(i.source_file_id)}</h4>
            <p>Needs attention</p>
            <p>{reason(i.source_file_id)}</p>
            {ownsRun && run.state === "review" && decisionButtons(i.source_file_id, null, i.allowed_actions ?? [], i.bulk_actions ?? {})}
          </article>
        ))}
      {!discovery &&
        deferred.map((i) => (
          <article className="accounts-bill" key={i.source_file_id}>
            <h4>{name(i.source_file_id)}</h4>
            <p>Not written</p>
            <p>{reason(i.source_file_id)}</p>
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
      <dialog ref={bulkDialog} className="bill-details" aria-label="Confirm similar bill decisions"
        onClose={() => setBulk(null)}>
        {bulk && <>
          <h4>{ACTION_LABELS[bulk.action]} · {bulk.count} similar bills</h4>
          <p>{bulk.description}</p>
          <p>This decision applies to all {bulk.count} matching open bills in this run.</p>
          {bulk.action === "supplier" && <p>Creates one supplier ledger and saves the authorized bills after native verification.</p>}
          <div className="accounts-toolbar">
            <button className="button button-primary" disabled={busy || controlState !== "active" || Boolean(loadError)}
              onClick={() => void act(`/api/tenants/${tenant}/attention/bills/${run.id}/${bulk.fileId}/bulk`, {
                action: bulk.action, proposal: bulk.proposal, preview_token: bulk.preview_token,
              }).then(() => bulkDialog.current?.close())}>Confirm for {bulk.count} bills</button>
            <button className="button button-ghost" disabled={busy} onClick={() => bulkDialog.current?.close()}>Cancel</button>
          </div>
        </>}
      </dialog>
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
