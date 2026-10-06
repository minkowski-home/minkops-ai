import { CatalogReview } from './CatalogReview';
import { DiscoveryReview } from './Discovery';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../contexts/AuthContext';
import { applyLocalPlan, applyTallyPlan, chooseFolder } from './localFiles';
import type { BillResult, Catalog, Run, Source } from './types';

function LegacyAccountsReview({ tenant, taskId }: { tenant: string; taskId: string }) {
  const { user } = useAuth(); const [run, setRun] = useState<Run | null>(null);
  const [edited, setEdited] = useState<Catalog | BillResult | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false); const [filter, setFilter] = useState('');
  const [clarifications,setClarifications] = useState<Record<string,string>>({});
  const applying = useRef(false); const automaticAttempt = useRef('');
  const previousState = useRef('');
  const base = `/api/tenants/${tenant}/accounts`;

  useEffect(() => {
    setRun(null); setEdited(null); previousState.current=''; automaticAttempt.current='';
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const loaded = await api<Run | null>(base + `/tasks/${taskId}/run`);
        if (!active) return;
        setRun(loaded);
        if (loaded?.result) setEdited((current) => !current || previousState.current !== 'review' ? structuredClone(loaded.result) : current);
        previousState.current = loaded?.state ?? '';
        if (loaded && !['completed','failed'].includes(loaded.state)) timer = setTimeout(() => void poll(), 2000);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : 'Could not load workflow.'); }
    };
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [base,taskId]);

  async function apply(loaded: Run) {
    if (!user || applying.current) return;
    applying.current = true; setBusy(true); setError('');
    try {
      const attempts = await Promise.allSettled([
        ...loaded.writes.filter((w) => !w.verified_at && !w.cancelled_at).map(w=>applyLocalPlan(tenant,loaded.id,w,user.csrf_token)),
        ...(loaded.tally_writes ?? []).filter(w=>!w.finished_at && !w.cancelled_at).map(w=>applyTallyPlan(tenant,loaded.id,w,user.csrf_token)),
      ]);
      const updated=await api<Run>(base + `/runs/${loaded.id}`);
      setRun(updated);setEdited(updated.result);previousState.current=updated.state;
      const failed = attempts.find(r=>r.status==='rejected');
      if (failed?.status==='rejected') throw failed.reason;
    } catch (e) { setError(e instanceof Error ? e.message : 'Local write needs attention.'); }
    finally { applying.current = false; setBusy(false); }
  }
  useEffect(() => {
    const attempt = run ? [...run.writes.filter(w=>!w.verified_at&&!w.cancelled_at).map(w=>w.id),...(run.tally_writes??[]).filter(w=>!w.finished_at&&!w.cancelled_at).map(w=>w.id)].join(':') : '';
    if (run?.state === 'writing' && automaticAttempt.current !== attempt && !applying.current) {
      automaticAttempt.current = attempt;
      void apply(run);
    }
    // The saved run ID triggers one automatic attempt. Retry is an explicit
    // gesture so the browser can request renewed local-folder permission.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id,run?.state,run?.writes,run?.tally_writes]);

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
  async function resolveBill(fileId:string,reject:boolean) {
    if(!run||!user)return;
    setBusy(true);setError('');
    try {
      const loaded=await api<Run>(base+`/runs/${run.id}/resolve-bill`,{method:'POST',body:JSON.stringify({file_id:fileId,user_input:clarifications[fileId]??'',reject})},user.csrf_token);
      setRun(loaded);setEdited(loaded.result);previousState.current=loaded.state;
    } catch(e) {setError(e instanceof Error?e.message:'Could not resolve this bill.');}
    finally {setBusy(false);}
  }
  if (!run) return error ? <p role="alert">{error}</p> : null;
  const binding = run.config.runtime_binding as { handler?: string } | undefined;
  const discovery = binding ? binding.handler === 'accounts.discovery' : run.workflow_key === 'source-discovery';
  return <section className="accounts-panel" aria-label="Workflow result"><h3>{discovery ? 'Source discovery' : 'Bill entry'}</h3>
    {['queued','executing'].includes(run.state) && <p role="status">Accounts desk is working. You can leave this page and return to the task.</p>}
    {run.state === 'failed' && <p role="alert">{run.error} Start a new run from the workflow after resolving the issue.</p>}
    {run.state === 'review' && edited && <>
      <div className="accounts-review-summary" aria-label="Review summary">
        <span>{discovery ? `${(edited as Catalog).sheets.length} sheets to confirm` : `${(edited as BillResult).records.filter(r=>!['saved','duplicate','rejected'].includes(r.status??'')).length} entries to review`}</span>
        {!discovery && <span>{(edited as BillResult).unresolved?.length ?? 0} bills need clarification</span>}
      </div>
      <p>{discovery ? 'Confirm the purpose, field meanings and record keys for each sheet.' : 'Approve, hold, reject or edit each bill. Other bills can continue while you resolve exceptions.'}</p>
      {discovery ? <>
        <label className="config-field">Find a workbook, sheet or table<input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search files, sheets or tables" /></label>
        <CatalogReview catalog={edited as Catalog} provenance={run.config.file_provenance as {id:string;path:string}[]} filter={filter} onChange={setEdited} />
      </> : <BillReview result={edited as BillResult} catalog={run.config.catalog_snapshot as Catalog} provenance={run.config.file_provenance as {id:string;path:string}[]} destinationLabel={(run.config.tally_target as {company?:string}|undefined)?.company} base={base} onChange={setEdited} />}
      {!discovery && <label className="accounts-check"><input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />I reviewed and acknowledge the unresolved findings.</label>}
      {!discovery && (edited as BillResult).unresolved?.map(issue=><div key={issue.source_file_id}>
        <p role="status">{issue.reason}</p>
        <label className="config-field">Clarify {provenanceName(run,issue.source_file_id)}<textarea maxLength={2000} value={clarifications[issue.source_file_id]??''} onChange={e=>setClarifications({...clarifications,[issue.source_file_id]:e.target.value})}/></label>
        <button className="button button-ghost" disabled={busy||!clarifications[issue.source_file_id]?.trim()} onClick={()=>void resolveBill(issue.source_file_id,false)}>Continue this bill</button>
        <button className="button button-ghost" disabled={busy} onClick={()=>void resolveBill(issue.source_file_id,true)}>Reject this bill</button>
      </div>)}
      <button className="button button-primary" disabled={busy} onClick={() => void approve()}>{busy ? 'Saving…' : discovery ? 'Confirm source mappings' : 'Approve selected entries'}</button>
    </>}
    {run.state === 'writing' && <><p>Saving your approved entries to their destinations. A connected PC keeps working while Minkops runs in its tray. For a browser-only folder, keep this page open.</p>
      <div className="accounts-toolbar"><button className="button button-primary" disabled={busy} onClick={() => void apply(run)}>{busy ? 'Saving and checking…' : 'Resume saves'}</button>
        {run.writes.some(w=>!w.verified_at&&!w.cancelled_at)&&<button className="button button-ghost" disabled={busy} onClick={() => void reconnect()}>Reconnect original folder</button>}
        <button className="button button-ghost" disabled={busy} onClick={() => void cancelWrites()}>Cancel remaining saves</button></div>
      <p className="quiet-state">Cancelling leaves any already applied entries in their destinations.</p></>}
    {run.state === 'completed' && <p role="status">{discovery ? 'Mappings confirmed. Bill entry can use this catalog.' : 'Bill entries checked. Exact duplicates were skipped without creating additional records.'}</p>}
    {run.state === 'completed' && !discovery && run.result && <details><summary>Checked bill entries · {(run.result as BillResult).records.length}</summary>
      <BillReview result={run.result as BillResult} catalog={run.config.catalog_snapshot as Catalog} provenance={run.config.file_provenance as {id:string;path:string}[]} destinationLabel={(run.config.tally_target as {company?:string}|undefined)?.company} base={base} onChange={()=>{}} />
    </details>}
    {!discovery && (run.result as BillResult | null)?.records.filter(r=>r.status==='duplicate').map((r,i)=><p role="status" key={i}>Duplicate skipped: {provenanceName(run,r.source_file_id)}</p>)}
    {(run.tally_writes ?? []).map(write=><p key={write.id}>{write.company} · {write.cancelled_at?'Cancelled':write.outcome ?? 'Waiting for your PC'}</p>)}
    {run.writes.map((write) => <details key={write.id}><summary>{write.path} · {write.verified_at ? 'Saved and verified' : write.cancelled_at ? 'Cancelled' : 'Pending local save'}</summary>
      <ul>{write.changes.map((change,i) => <li key={i}>{change.sheet}{change.table ? ` / ${change.table}` : ''} · row {change.row} · {change.operation}</li>)}</ul></details>)}
    {error && <p role="alert" className="form-message">{error}</p>}
  </section>;
}


function BillReview({ result, catalog, provenance, destinationLabel, base, onChange }: { result: BillResult; catalog: Catalog; provenance: {id:string;path:string}[]; destinationLabel?:string; base:string; onChange: (value: BillResult) => void }) {
  const change = (index: number, key: string, value: string | number | boolean | null) => { const next = structuredClone(result); next.records[index].data[key]=value; onChange(next); };
  return <div className="accounts-bills">{result.findings.length > 0 && <details><summary>Extraction notes · {result.findings.length}</summary><ul>{result.findings.map((v,i) => <li key={i}>{v}</li>)}</ul></details>}
    {result.unresolved?.map((issue) => <p role="alert" key={issue.source_file_id}>Bill needs clarification: {provenance.find((f) => f.id===issue.source_file_id)?.path}: {issue.reason}</p>)}
    {result.records.map((record,index) => {
      const readonly = ['saved','duplicate','rejected'].includes(record.status??'');
      const columns = catalog.sheets.find((s) => s.file_id===record.destination_file_id && s.sheet===record.sheet && s.table==record.table)?.columns ?? [];
      return <article key={index} className="accounts-bill"><h4>Bill {index+1} → {record.sheet}{record.table ? ` / ${record.table}` : ''}</h4>
      <p>{record.status ?? 'Awaiting review'}</p>
      {record.current_excel&&<details><summary>Observed destination values</summary><dl>{Object.entries(record.current_excel).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value??'')}</dd></div>)}</dl></details>}
      {record.current&&<details><summary>Observed Tally values</summary><p>{record.current.vendor} · {record.current.invoice_number} · {record.current.date}</p><dl>{record.current.entries.map((entry,i)=><div key={i}><dt>{entry.ledger}</dt><dd>{(entry.amount/100).toFixed(2)}</dd></div>)}</dl></details>}
      {!['saved','duplicate','rejected'].includes(record.status??'') && <label className="config-field">Review decision<select value={record.decision??'approve'} onChange={e=>{const next=structuredClone(result);next.records[index].decision=e.target.value as 'approve'|'hold'|'reject';onChange(next);}}><option value="approve">Approve</option><option value="hold">Hold for correction</option><option value="reject">Reject</option></select></label>}
      <p><a href={`${base}/files/${record.source_file_id}/content`} target="_blank" rel="noreferrer">View source: {provenance.find((f) => f.id===record.source_file_id)?.path ?? `Bill ${index+1}`}</a></p>
      <p className="quiet-state">Destination: {destinationLabel ?? provenance.find((f) => f.id===record.destination_file_id)?.path} · {record.sheet}{record.table ? ` / ${record.table}` : ''}</p>
      <label className="config-field">Entry action<select disabled={readonly} value={record.operation} onChange={(e) => { const next=structuredClone(result); next.records[index].operation=e.target.value as 'append'|'update'; onChange(next); }}><option value="append">Append a new entry</option><option value="update">Edit the entry matching its confirmed keys</option></select></label>
      <div className="accounts-field-grid">{Object.entries(record.data).map(([key,value]) => {
        const type = columns.find((c) => c.name===key)?.type;
        const numeric = type==='number' || type==='integer';
        return <label key={key}>{key}
          {type === 'boolean' ? <select disabled={readonly} value={value===null ? '' : String(value)} onChange={(e) => change(index,key,e.target.value==='' ? null : e.target.value==='true')}><option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option></select> :
            <input disabled={readonly||Boolean(record.derived_fields?.[key])} type={numeric ? 'number' : 'text'} step="any" value={value===null ? '' : String(value)} onChange={(e) => change(index,key,e.target.value==='' ? null : numeric ? Number(e.target.value) : e.target.value)} />}
          {record.derived_fields?.[key] && <small>{record.derived_fields[key]}</small>}
        </label>;
      })}</div>
      {record.findings.length > 0 && <div className="accounts-findings"><strong>Needs review</strong><ul>{record.findings.map((finding,i) => <li key={i}>{finding}</li>)}</ul></div>}
      <details><summary>Source evidence · {record.evidence.length} fields</summary><dl>{record.evidence.map((e,i) => <div key={i}><dt>{e.field} · page {e.page}</dt><dd>{e.quote}</dd></div>)}</dl></details>
    </article>;
    })}
  </div>;
}

function provenanceName(run:Run,id:string) {
  return (run.config.file_provenance as {id:string;path:string}[]).find(f=>f.id===id)?.path ?? 'Bill';
}

export function AccountsReview({tenant,taskId}:{tenant:string;taskId:string}) {
  const [native,setNative]=useState<boolean|null>(null);const [error,setError]=useState('');
  useEffect(()=>{let active=true;void api<unknown>(`/api/tenants/${tenant}/discovery/tasks/${taskId}`).then(r=>{if(active)setNative(Boolean(r));}).catch((e:Error)=>{if(active)setError(e.message);});return()=>{active=false;};},[tenant,taskId]);
  if(error)return <p role="alert">{error}</p>;
  if(native===null)return null;
  return native?<DiscoveryReview tenant={tenant} taskId={taskId}/>:<LegacyAccountsReview tenant={tenant} taskId={taskId}/>;
}
