import { DiscoveryLaunch } from './Discovery';
import { presentationFor } from '../workflows/presentation';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type Workflow } from '../api';
import { useAuth } from '../contexts/AuthContext';
import { chooseFolder, refreshFolder, supportsLocalFolder } from './localFiles';
import type { Run, Source, SavedCatalog } from './types';
import { LoadingIndicator, RetryMessage, Spinner } from '../components/Feedback';

interface NativeCatalog { id:string; ready:boolean; device_id:string; config:{tally:{company?:string}|null};catalog?:{format_version?:string;sources:{tool:string;snapshot?:{companies?:{company:string;company_guid:string}[]}}[]} }
const discoveredCompanies = (catalog:NativeCatalog|null) => catalog?.catalog?.sources.flatMap(s=>s.tool==='tally' ? s.snapshot?.companies ?? [] : []) ?? [];

function BillLaunch({ tenant, routeSlug, workflow }: { tenant: string; routeSlug: string; workflow: Workflow }) {
  const { user } = useAuth(); const navigate = useNavigate();
  const [sources, setSources] = useState<Source[]>([]);
  const [catalogs, setCatalogs] = useState<SavedCatalog[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [catalogId, setCatalogId] = useState('');
  const [outputMode,setOutputMode] = useState(String(workflow.config_values.output_mode ?? 'excel_in_place'));
  const [nativeCatalog,setNativeCatalog] = useState<NativeCatalog|null>(null);
  const [companyMode,setCompanyMode] = useState<'locked'|'infer'>('infer');
  const [lockedCompanyGuid,setLockedCompanyGuid] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [inputFormat, setInputFormat] = useState(String(workflow.config_values.input_format ?? 'mixed'));
  const [reviewMode, setReviewMode] = useState(String(workflow.config_values.review_mode ?? 'all_outputs'));
  const [checks, setChecks] = useState(['vendor_match','duplicate','totals','cost_codes']);
  const enabledOutputs = workflow.config_schema.properties.output_mode?.['x-enabled-options'];
  const base = `/api/tenants/${tenant}/accounts`;
  const preferences = `${tenant}:${workflow.key}:selections:v1`;
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(''), [attempt, setAttempt] = useState(0);

  async function refresh() {
    const [loadedSources, loadedCatalogs] = await Promise.all([api<Source[]>(base + '/sources'), api<SavedCatalog[]>(base + '/catalogs')]);
    setSources(loadedSources); setCatalogs(loadedCatalogs.filter(c=>c.catalog.sheets.some(s=>s.role==='destination')));
    setCatalogId((current) => current || loadedCatalogs[0]?.id || '');
    let saved: string[] = [];
    try { saved = JSON.parse(localStorage.getItem(preferences) ?? '[]') as string[]; } catch { /* Ignore old preference formats. */ }
    const eligible = loadedSources.flatMap((s) => s.files.filter((f) => /\.(pdf|png|jpe?g|webp)$/i.test(f.path))
      .map((f) => ({ id: f.id, key: `${s.id}:${f.path}` })));
    setSelected(eligible.filter((f) => saved.length ? saved.includes(f.key) : true).map((f) => f.id));
  }
  useEffect(() => { let active = true;
    setLoading(true); setLoadError('');
    void Promise.all([api<Source[]>(base + '/sources'), api<SavedCatalog[]>(base + '/catalogs'), api<NativeCatalog|null>(`/api/tenants/${tenant}/discovery/latest`)]).then(([ss, cc, native]) => {
      if (!active) return;
      setNativeCatalog(native); setLockedCompanyGuid(discoveredCompanies(native)[0]?.company_guid ?? '');
      const destinations=cc.filter(c=>c.catalog.sheets.some(s=>s.role==='destination'));
      setSources(ss); setCatalogs(destinations); setCatalogId(destinations[0]?.id ?? '');
      let saved: string[] = []; try { saved = JSON.parse(localStorage.getItem(preferences) ?? '[]') as string[]; } catch { /* Old preferences are optional. */ }
      setSelected(ss.flatMap((s) => s.files.filter((f) => (/\.(pdf|png|jpe?g|webp)$/i.test(f.path)) && (!saved.length || saved.includes(`${s.id}:${f.path}`))).map((f) => f.id)));
    }).catch((e: Error) => { if (active) setLoadError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [base, preferences, tenant, attempt]);

  async function action(work: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await work(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Could not complete this action.'); }
    finally { setBusy(false); }
  }
  async function upload(files: FileList | null) {
    if (!files || !user) return;
    await action(async () => {
      const form = new FormData(); form.append('paths', JSON.stringify(Array.from(files, (f) => f.name)));
      Array.from(files).forEach((f) => form.append('files', f));
      await api(base + '/sources', { method: 'POST', body: form }, user.csrf_token);
    });
  }
  async function launch() {
    if (!user) return;
    setBusy(true); setError('');
    try {
      localStorage.setItem(preferences, JSON.stringify(sources.flatMap((s) => s.files.filter((f) => selected.includes(f.id)).map((f) => `${s.id}:${f.path}`))));
      localStorage.setItem(`${tenant}:bill-entry:target:v1`,JSON.stringify({output_mode:outputMode,catalog_id:catalogId,discovery_id:nativeCatalog?.id,company_mode:companyMode,locked_company_guid:companyMode==='locked'?lockedCompanyGuid:null}));
      const run = await api<Run>(base + '/runs', { method: 'POST', body: JSON.stringify({
        key: workflow.key, request_key: crypto.randomUUID(), file_ids: selected,
        catalog_id: outputMode==='tally_in_place' ? null : catalogId,
        config: { input_format: inputFormat, review_mode: outputMode==='tally_in_place'?'all_outputs':reviewMode, output_mode: outputMode, checks, ...(outputMode==='tally_in_place'?{discovery_id:nativeCatalog?.id,company_mode:companyMode,locked_company_guid:companyMode==='locked'?lockedCompanyGuid:null}:{}) },
      }) }, user.csrf_token);
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start workflow.'); }
    finally { setBusy(false); }
  }
  if (loading) return <section className="accounts-panel"><LoadingIndicator>Loading bill sources…</LoadingIndicator></section>;
  if (loadError) return <section className="accounts-panel"><RetryMessage onRetry={() => setAttempt(value => value + 1)}>{loadError}</RetryMessage></section>;
  return <section className="accounts-panel" aria-label="Run workflow">
    <div className="section-heading"><div><h3>Enter bills</h3>
      <p>Read bills in parallel, review entries, and save to your connected Excel or Tally.</p></div></div>
    <div className="accounts-toolbar">
      <button className="button button-ghost" disabled={busy || !supportsLocalFolder()} onClick={() => user && void action(() => chooseFolder(tenant,user.csrf_token))}>Connect local folder</button>
      <label className="button button-ghost">Upload files<input aria-label="Upload workflow files" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp" disabled={busy} onChange={(e) => { void upload(e.target.files); e.target.value = ''; }} /></label>
    </div>
    <p className="quiet-state">{window.minkopsDesktop ? 'Folders remain connected on this PC.' : 'Folder access stays in this browser.'} Excel destinations require a connected folder. Supported: .xlsx, PDF, PNG, JPEG and WebP. Other file types are skipped.</p>
    {!supportsLocalFolder() && <p role="status">Open this workspace in Chrome or Edge to update local Excel files.</p>}
    <div className="accounts-sources">{sources.map((source) => {
      const eligible = source.files.filter((f) => /\.(pdf|png|jpe?g|webp)$/i.test(f.path));
      if (!eligible.length) return null;
      return <details key={source.id} open={sources.length < 4}><summary>{source.label} · {eligible.length} files · {source.writable ? 'Local folder' : 'Uploaded'}</summary>
        {source.writable && <div className="accounts-toolbar"><button className="button button-ghost" disabled={busy} onClick={() => user && void action(() => refreshFolder(tenant,source,user.csrf_token))}>Refresh folder</button>
          <button className="button button-ghost" disabled={busy} onClick={() => user && void action(() => chooseFolder(tenant,user.csrf_token,source))}>Reconnect folder</button></div>}
        <div className="accounts-file-list">{eligible.map((file) => <label key={file.id}><input type="checkbox" checked={selected.includes(file.id)} onChange={(e) => setSelected((old) => e.target.checked ? [...old,file.id] : old.filter((id) => id !== file.id))} />{file.path}</label>)}</div>
      </details>;
    })}</div>
    {!sources.length && <p className="quiet-state">Connect a folder to begin. For the first test, select the synthetic mock-workspace folder.</p>}
    <details className="accounts-config"><summary>Run configuration</summary><div className="accounts-field-grid">
        <label>Input types<select value={inputFormat} onChange={(e) => setInputFormat(e.target.value)}><option value="mixed">PDFs and images</option><option value="pdf">PDFs</option><option value="image">Images</option></select></label>
        <label>Review policy<select disabled={outputMode==='tally_in_place'} value={outputMode==='tally_in_place'?'all_outputs':reviewMode} onChange={(e) => setReviewMode(e.target.value)}><option value="all_outputs">Approve every output</option><option value="only_exceptions">Only exceptions</option></select></label>
        <label>Output platform<select value={outputMode} onChange={e=>setOutputMode(e.target.value)}>{[['excel_in_place','Excel · update existing sheets'],['tally_in_place','Tally · purchase vouchers'],['both_in_place','Both · Excel and Tally']].map(([value,label])=><option key={value} value={value} disabled={Boolean(enabledOutputs && !enabledOutputs.includes(value))}>{label}</option>)}</select></label>
        {enabledOutputs && <p className="quiet-state">This workspace saves bills to Tally only. Excel destinations are disabled.</p>}
        {outputMode==='tally_in_place'?<p role="status">{nativeCatalog?.ready&&discoveredCompanies(nativeCatalog).length?`${discoveredCompanies(nativeCatalog).length} discovered companies available`:'Run and confirm complete Tally Source Discovery first.'}</p>:
        <label>Confirmed sources<select value={catalogId} onChange={(e) => setCatalogId(e.target.value)}><option value="">Run source discovery first</option>{catalogs.map((c) => <option key={c.id} value={c.id}>{new Date(c.confirmed_at).toLocaleString()} · {c.catalog.sheets.length} sheets</option>)}</select></label>}
        {outputMode==='tally_in_place'&&<><label>Company selection<select value={companyMode} onChange={e=>setCompanyMode(e.target.value as 'locked'|'infer')}><option value="infer">Infer from each bill · any discovered company</option><option value="locked">Use one company for this run</option></select></label>{companyMode==='locked'&&<label>Company for all bills<select value={lockedCompanyGuid} onChange={e=>setLockedCompanyGuid(e.target.value)}><option value="">Choose a company</option>{discoveredCompanies(nativeCatalog).map(c=><option key={c.company_guid} value={c.company_guid}>{c.company}</option>)}</select></label>}</>}
        {outputMode!=='tally_in_place'&&<fieldset><legend>Reference checks</legend>{['vendor_match','duplicate','totals','cost_codes'].map((check) => <label key={check}><input type="checkbox" checked={checks.includes(check)} onChange={(e) => setChecks((old) => e.target.checked ? [...old,check] : old.filter((v) => v !== check))} />{check.replaceAll('_',' ')}</label>)}</fieldset>}
    </div></details>
    {error && <p role="alert" className="form-message">{error}</p>}
    <button className="button button-primary" disabled={busy || workflow.status !== 'active' || !selected.length || (outputMode==='tally_in_place'? !nativeCatalog?.ready||!discoveredCompanies(nativeCatalog).length||(companyMode==='locked'&&!lockedCompanyGuid) : !catalogId)} onClick={() => void launch()}>{busy && <Spinner />}{busy ? 'Working…' : `Run ${workflow.name.toLowerCase()}`}</button>
    <span className="quiet-state"> {selected.length} files selected</span>
  </section>;
}

/** The dashboard runs saved selections with editable tenant defaults. */
export function AccountsQuickRun({ tenant, routeSlug, workflow }: { tenant: string; routeSlug: string; workflow: Workflow }) {
  const { user } = useAuth(); const navigate = useNavigate();
  const [busy,setBusy] = useState(false); const [error,setError] = useState('');
  async function run() {
    if (!user || busy) return;
    setBusy(true); setError('');
    const base = `/api/tenants/${tenant}/accounts`;
    const discovery = presentationFor(workflow) === 'accounts-discovery';
    try {
      if (discovery) {
        const latest=await api<{device_id:string;config:Record<string,unknown>}|null>(`/api/tenants/${tenant}/discovery/latest`);
        if (!latest || latest.config.depth !== 'client_context') { navigate(`/${routeSlug}/workflows/${workflow.id}`); return; }
        const launched=await api<Run>(`/api/tenants/${tenant}/discovery/runs`,{method:'POST',body:JSON.stringify({device_id:latest.device_id,config:latest.config,request_key:crypto.randomUUID()})},user.csrf_token);
        navigate(`/${routeSlug}/tasks/${launched.task_id}`); return;
      }
      const [sources,catalogs] = await Promise.all([api<Source[]>(base+'/sources'),api<SavedCatalog[]>(base+'/catalogs')]);
      let target:{output_mode?:string;catalog_id?:string;discovery_id?:string;company_mode?:string;locked_company_guid?:string|null}={};
      try { target=JSON.parse(localStorage.getItem(`${tenant}:bill-entry:target:v1`)??'{}') as typeof target; } catch { /* Setup is authoritative. */ }
      const tally=target.output_mode==='tally_in_place';
      let selections: string[] = [];
      try {
        const saved: unknown = JSON.parse(localStorage.getItem(`${tenant}:${workflow.key}:selections:v1`) ?? '[]');
        if (Array.isArray(saved) && saved.every((v) => typeof v === 'string')) selections=saved;
      } catch { /* Preferences are optional; setup remains available. */ }
      if (!selections.length || (tally ? !target.discovery_id : !catalogs.length)) {
        navigate(`/${routeSlug}/workflows/${workflow.id}`); return;
      }
      if (tally) {
        const [selectedTarget,latest] = await Promise.all([
          api<NativeCatalog>(`/api/tenants/${tenant}/discovery/runs/${target.discovery_id}`),
          api<NativeCatalog|null>(`/api/tenants/${tenant}/discovery/latest`),
        ]);
        const identities=(catalog:NativeCatalog|null)=>discoveredCompanies(catalog).map(c=>c.company_guid).sort().join('|');
        if (!latest?.ready || !identities(latest) || latest.device_id!==selectedTarget.device_id || identities(latest)!==identities(selectedTarget)) {
          navigate(`/${routeSlug}/workflows/${workflow.id}`);return;
        }
        target.discovery_id=latest.id;
      }
      // Refresh the selected local source before recognition so newly changed
      // bytes cannot silently be treated as the earlier snapshot.
      const selectedSources = sources.filter((source) => source.files.some((file) => selections.includes(`${source.id}:${file.path}`)));
      const refreshed = [];
      for (const source of selectedSources) refreshed.push(source.writable ? await refreshFolder(tenant,source,user.csrf_token) : source);
      const files = refreshed.flatMap((source) => source.files.filter((file) => selections.includes(`${source.id}:${file.path}`) &&
        /\.(pdf|png|jpe?g|webp)$/i.test(file.path)).map((file) => file.id));
      if (!files.length) throw new Error('Your saved selection is unavailable. Open workflow details to select files.');
      const loaded = await api<Run>(base+'/runs', {method:'POST',body:JSON.stringify({
        key:workflow.key,request_key:crypto.randomUUID(),file_ids:files,catalog_id:tally ? null : target.catalog_id??catalogs[0].id,
        config:tally?{output_mode:'tally_in_place',discovery_id:target.discovery_id,company_mode:target.company_mode??'infer',locked_company_guid:target.locked_company_guid??null}:{output_mode:'excel_in_place'},
      })},user.csrf_token);
      navigate(`/${routeSlug}/tasks/${loaded.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Open workflow details to reconnect your folder.'); }
    finally { setBusy(false); }
  }
  return <div><button className="button button-primary" disabled={busy} onClick={() => void run()}>{busy && <Spinner />}{busy ? 'Starting…' : 'Run workflow'}</button>
    {error && <p role="alert" className="form-message">{error}</p>}</div>;
}

export function AccountsLaunch(props:{tenant:string;routeSlug:string;workflow:Workflow}) {
  return presentationFor(props.workflow)==='accounts-discovery'?<DiscoveryLaunch {...props}/>:<BillLaunch {...props}/>;
}
