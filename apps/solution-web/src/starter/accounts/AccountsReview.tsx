import { CatalogReview } from './CatalogReview';
import { DiscoveryReview } from './Discovery';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../contexts/AuthContext';
import { applyLocalPlan, chooseFolder } from './localFiles';
import type { BillResult, Catalog, Run, Source } from './types';

function LegacyAccountsReview({ tenant, taskId }: { tenant: string; taskId: string }) {
  const { user } = useAuth(); const [run, setRun] = useState<Run | null>(null);
  const [edited, setEdited] = useState<Catalog | BillResult | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false); const [filter, setFilter] = useState('');
  const applying = useRef(false); const automaticAttempt = useRef('');
  const base = `/api/tenants/${tenant}/accounts`;

  useEffect(() => {
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const loaded = await api<Run | null>(base + `/tasks/${taskId}/run`);
        if (!active) return;
        setRun(loaded);
        if (loaded?.result) setEdited((current) => current ?? structuredClone(loaded.result));
        if (loaded && !['completed','failed'].includes(loaded.state)) timer = setTimeout(() => void poll(), 2000);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : 'Could not load workflow.'); }
    };
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [base,taskId]);

  async function apply(loaded: Run) {
    if (!user || applying.current) return;
    applying.current = true; setBusy(true); setError('');
    try {
      for (const write of loaded.writes.filter((w) => !w.verified_at && !w.cancelled_at)) await applyLocalPlan(tenant,loaded.id,write,user.csrf_token);
      setRun(await api<Run>(base + `/runs/${loaded.id}`));
    } catch (e) { setError(e instanceof Error ? e.message : 'Local write needs attention.'); }
    finally { applying.current = false; setBusy(false); }
  }
  useEffect(() => {
    if (run?.state === 'writing' && automaticAttempt.current !== run.id && !applying.current) {
      automaticAttempt.current = run.id;
      void apply(run);
    }
    // The saved run ID triggers one automatic attempt. Retry is an explicit
    // gesture so the browser can request renewed local-folder permission.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id,run?.state]);

  async function approve() {
    if (!run || !user || !edited) return;
    setBusy(true); setError('');
    try {
      const loaded = await api<Run>(base + `/runs/${run.id}/approve`, { method:'POST',body:JSON.stringify({result:edited,acknowledge_findings:acknowledged}) },user.csrf_token);
      setRun(loaded); setEdited(loaded.result);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not approve.'); }
    finally { setBusy(false); }
  }
  async function reconnect() {
    if (!run || !user) return;
    setBusy(true); setError('');
    try {
      const sources = await api<Source[]>(base + '/sources');
      const ids = new Set(run.writes.filter((w) => !w.verified_at).map((w) => w.source_id));
      for (const id of ids) {
        const source = sources.find((s) => s.id === id);
        if (!source) throw new Error('Local source was removed.');
        await chooseFolder(tenant,user.csrf_token,source);
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not reconnect.'); }
    finally { setBusy(false); }
  }
  async function cancelWrites() {
    if (!run || !user) return;
    setBusy(true); setError('');
    try { setRun(await api<Run>(base+`/runs/${run.id}/cancel-writes`, {method:'POST'},user.csrf_token)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not cancel pending writes.'); }
    finally { setBusy(false); }
  }
  if (!run) return error ? <p role="alert">{error}</p> : null;
  const binding = run.config.runtime_binding as { handler?: string } | undefined;
  const discovery = binding ? binding.handler === 'accounts.discovery' : run.workflow_key === 'source-discovery';
  return <section className="accounts-panel" aria-label="Workflow result"><h3>{discovery ? 'Source discovery' : 'Bill entry'}</h3>
    {['queued','executing'].includes(run.state) && <p role="status">Accounts desk is working. You can leave this page and return to the task.</p>}
    {run.state === 'failed' && <p role="alert">{run.error} Start a new run from the workflow after resolving the issue.</p>}
    {run.state === 'review' && edited && <>
      <div className="accounts-review-summary" aria-label="Review summary">
        <span>{discovery ? `${(edited as Catalog).sheets.length} sheets to confirm` : `${(edited as BillResult).records.length} entries to review`}</span>
        {!discovery && <span>{(edited as BillResult).unresolved?.length ?? 0} destinations need clarification</span>}
      </div>
      <p>{discovery ? 'Confirm the purpose, field meanings and record keys for each sheet.' : 'Review the proposed entries and source evidence before saving to Excel.'}</p>
      {discovery ? <>
        <label className="config-field">Find a workbook, sheet or table<input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search files, sheets or tables" /></label>
        <CatalogReview catalog={edited as Catalog} provenance={run.config.file_provenance as {id:string;path:string}[]} filter={filter} onChange={setEdited} />
      </> : <BillReview result={edited as BillResult} catalog={run.config.catalog_snapshot as Catalog} provenance={run.config.file_provenance as {id:string;path:string}[]} base={base} onChange={setEdited} />}
      {!discovery && <label className="accounts-check"><input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />I reviewed and acknowledge the unresolved findings.</label>}
      <button className="button button-primary" disabled={busy || (!discovery && Boolean((edited as BillResult).unresolved?.length))} onClick={() => void approve()}>{busy ? 'Savingâ€¦' : discovery ? 'Confirm source mappings' : 'Approve Excel entries'}</button>
    </>}
    {run.state === 'writing' && <><p>Saving your approved entries to the original workbooks. A connected PC keeps working while Minkops runs in its tray. For a browser-only folder, keep this page open.</p>
      <div className="accounts-toolbar"><button className="button button-primary" disabled={busy} onClick={() => void apply(run)}>{busy ? 'Saving and checkingâ€¦' : 'Resume saves'}</button>
        <button className="button button-ghost" disabled={busy} onClick={() => void reconnect()}>Reconnect original folder</button>
        <button className="button button-ghost" disabled={busy} onClick={() => void cancelWrites()}>Cancel remaining saves</button></div>
      <p className="quiet-state">Cancelling leaves any already applied entries in the workbook.</p></>}
    {run.state === 'completed' && <p role="status">{discovery ? 'Mappings confirmed. Bill entry can use this catalog.' : 'Excel entries saved in place and verified.'}</p>}
    {run.writes.map((write) => <details key={write.id}><summary>{write.path} Â· {write.verified_at ? 'Saved and verified' : write.cancelled_at ? 'Cancelled' : 'Pending local save'}</summary>
      <ul>{write.changes.map((change,i) => <li key={i}>{change.sheet}{change.table ? ` / ${change.table}` : ''} Â· row {change.row} Â· {change.operation}</li>)}</ul></details>)}
    {error && <p role="alert" className="form-message">{error}</p>}
  </section>;
}


function BillReview({ result, catalog, provenance, base, onChange }: { result: BillResult; catalog: Catalog; provenance: {id:string;path:string}[]; base:string; onChange: (value: BillResult) => void }) {
  const change = (index: number, key: string, value: string | number | boolean | null) => { const next = structuredClone(result); next.records[index].data[key]=value; onChange(next); };
  return <div className="accounts-bills">{result.findings.length > 0 && <ul>{result.findings.map((v,i) => <li key={i}>{v}</li>)}</ul>}
    {result.unresolved?.map((issue) => <p role="alert" key={issue.source_file_id}>Destination needs clarification for {provenance.find((f) => f.id===issue.source_file_id)?.path}: {issue.reason} Update source mappings and run bill entry again.</p>)}
    {result.records.map((record,index) => {
      const columns = catalog.sheets.find((s) => s.file_id===record.destination_file_id && s.sheet===record.sheet && s.table==record.table)?.columns ?? [];
      return <article key={index} className="accounts-bill"><h4>Bill {index+1} â†’ {record.sheet}{record.table ? ` / ${record.table}` : ''}</h4>
      <p><a href={`${base}/files/${record.source_file_id}/content`} target="_blank" rel="noreferrer">View source: {provenance.find((f) => f.id===record.source_file_id)?.path ?? `Bill ${index+1}`}</a></p>
      <p className="quiet-state">Destination: {provenance.find((f) => f.id===record.destination_file_id)?.path} Â· {record.sheet}{record.table ? ` / ${record.table}` : ''}</p>
      <label className="config-field">Entry action<select value={record.operation} onChange={(e) => { const next=structuredClone(result); next.records[index].operation=e.target.value as 'append'|'update'; onChange(next); }}><option value="append">Append a new entry</option><option value="update">Edit the entry matching its confirmed keys</option></select></label>
      <div className="accounts-field-grid">{Object.entries(record.data).map(([key,value]) => {
        const type = columns.find((c) => c.name===key)?.type;
        const numeric = type==='number' || type==='integer';
        return <label key={key}>{key}
          {type === 'boolean' ? <select value={value===null ? '' : String(value)} onChange={(e) => change(index,key,e.target.value==='' ? null : e.target.value==='true')}><option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option></select> :
            <input disabled={Boolean(record.derived_fields?.[key])} type={numeric ? 'number' : 'text'} step="any" value={value===null ? '' : String(value)} onChange={(e) => change(index,key,e.target.value==='' ? null : numeric ? Number(e.target.value) : e.target.value)} />}
          {record.derived_fields?.[key] && <small>{record.derived_fields[key]}</small>}
        </label>;
      })}</div>
      {record.findings.length > 0 && <div className="accounts-findings"><strong>Needs review</strong><ul>{record.findings.map((finding,i) => <li key={i}>{finding}</li>)}</ul></div>}
      <details><summary>Source evidence Â· {record.evidence.length} fields</summary><dl>{record.evidence.map((e,i) => <div key={i}><dt>{e.field} Â· page {e.page}</dt><dd>{e.quote}</dd></div>)}</dl></details>
    </article>;
    })}
  </div>;
}

export function AccountsReview({tenant,taskId}:{tenant:string;taskId:string}) {
  const [native,setNative]=useState<boolean|null>(null);const [error,setError]=useState('');
  useEffect(()=>{let active=true;void api<unknown>(`/api/tenants/${tenant}/discovery/tasks/${taskId}`).then(r=>{if(active)setNative(Boolean(r));}).catch((e:Error)=>{if(active)setError(e.message);});return()=>{active=false;};},[tenant,taskId]);
  if(error)return <p role="alert">{error}</p>;
  if(native===null)return null;
  return native?<DiscoveryReview tenant={tenant} taskId={taskId}/>:<LegacyAccountsReview tenant={tenant} taskId={taskId}/>;
}
