import { DiscoveryLaunch } from './Discovery';
import { presentationFor } from '../workflows/presentation';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type Workflow } from '../api';
import { useAuth } from '../contexts/AuthContext';
import { chooseFolder, refreshFolder, supportsLocalFolder } from './localFiles';
import type { Run, Source, SavedCatalog } from './types';

interface NativeCatalog { id:string; ready:boolean; config:{tally:{company:string}|null} }

function LegacyAccountsLaunch({ tenant, routeSlug, workflow }: { tenant: string; routeSlug: string; workflow: Workflow }) {
  const { user } = useAuth(); const navigate = useNavigate();
  const [sources, setSources] = useState<Source[]>([]);
  const [catalogs, setCatalogs] = useState<SavedCatalog[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [catalogId, setCatalogId] = useState('');
  const [outputMode,setOutputMode] = useState(String(workflow.config_values.output_mode ?? 'excel_in_place'));
  const [nativeCatalog,setNativeCatalog] = useState<NativeCatalog|null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [inputFormat, setInputFormat] = useState(String(workflow.config_values.input_format ?? 'mixed'));
  const [reviewMode, setReviewMode] = useState(String(workflow.config_values.review_mode ?? 'all_outputs'));
  const [maxFiles, setMaxFiles] = useState(Number(workflow.config_values.max_files ?? 100));
  const [discoveryDepth,setDiscoveryDepth] = useState(String(workflow.config_values.discovery_depth ?? 'business_mappings'));
  const [refreshMode,setRefreshMode] = useState('initial');
  const [checks, setChecks] = useState(['vendor_match','duplicate','totals','cost_codes']);
  const discovery = presentationFor(workflow) === 'accounts-discovery';
  const base = `/api/tenants/${tenant}/accounts`;
  const preferences = `${tenant}:${workflow.key}:selections:v1`;
  useEffect(()=>{let active=true;void api<NativeCatalog|null>(`/api/tenants/${tenant}/discovery/latest`).then(c=>{if(active)setNativeCatalog(c);}).catch((e:Error)=>{if(active)setError(e.message);});return()=>{active=false;};},[tenant]);

  async function refresh() {
    const [loadedSources, loadedCatalogs] = await Promise.all([api<Source[]>(base + '/sources'), api<SavedCatalog[]>(base + '/catalogs')]);
    setSources(loadedSources); setCatalogs(loadedCatalogs.filter(c=>c.catalog.sheets.some(s=>s.role==='destination')));
    setCatalogId((current) => current || loadedCatalogs[0]?.id || '');
    let saved: string[] = [];
    try { saved = JSON.parse(localStorage.getItem(preferences) ?? '[]') as string[]; } catch { /* Ignore old preference formats. */ }
    const eligible = loadedSources.flatMap((s) => s.files.filter((f) => discovery ? /\.xlsx$/i.test(f.path) : /\.(pdf|png|jpe?g|webp)$/i.test(f.path))
      .map((f) => ({ id: f.id, key: `${s.id}:${f.path}` })));
    setSelected(eligible.filter((f) => saved.length ? saved.includes(f.key) : true).map((f) => f.id));
  }
  useEffect(() => { let active = true;
    void Promise.all([api<Source[]>(base + '/sources'), api<SavedCatalog[]>(base + '/catalogs')]).then(([ss, cc]) => {
      if (!active) return;
      const destinations=cc.filter(c=>c.catalog.sheets.some(s=>s.role==='destination'));
      setSources(ss); setCatalogs(destinations); setCatalogId(destinations[0]?.id ?? '');
      let saved: string[] = []; try { saved = JSON.parse(localStorage.getItem(preferences) ?? '[]') as string[]; } catch { /* Old preferences are optional. */ }
      setSelected(ss.flatMap((s) => s.files.filter((f) => (discovery ? /\.xlsx$/i.test(f.path) : /\.(pdf|png|jpe?g|webp)$/i.test(f.path)) && (!saved.length || saved.includes(`${s.id}:${f.path}`))).map((f) => f.id)));
    }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [base, preferences, discovery]);

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
      if (!discovery) localStorage.setItem(`${tenant}:bill-entry:target:v1`,JSON.stringify({output_mode:outputMode,catalog_id:catalogId,discovery_id:nativeCatalog?.id}));
      const run = await api<Run>(base + '/runs', { method: 'POST', body: JSON.stringify({
        key: workflow.key, request_key: crypto.randomUUID(), file_ids: selected,
        catalog_id: discovery || outputMode==='tally_in_place' ? null : catalogId,
        config: discovery ? { max_files: maxFiles, discovery_depth:discoveryDepth, refresh_mode:refreshMode } : { input_format: inputFormat, review_mode: outputMode==='tally_in_place'?'all_outputs':reviewMode, output_mode: outputMode, checks, ...(outputMode==='tally_in_place'?{discovery_id:nativeCatalog?.id}:{}) },
      }) }, user.csrf_token);
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start workflow.'); }
    finally { setBusy(false); }
  }
  return <section className="accounts-panel" aria-label="Run workflow">
    <div className="section-heading"><div><h3>{discovery ? 'Discover your Excel sources' : 'Enter bills'}</h3>
      <p>{discovery ? 'Inspect once, confirm the mappings, and refresh when your sources change.' : 'Read bills in parallel, review entries, and save to your connected Excel or Tally.'}</p></div></div>
    <div className="accounts-toolbar">
      <button className="button button-ghost" disabled={busy || !supportsLocalFolder()} onClick={() => user && void action(() => chooseFolder(tenant,user.csrf_token))}>Connect local folder</button>
      <label className="button button-ghost">Upload files<input aria-label="Upload workflow files" type="file" multiple accept={discovery ? '.xlsx' : '.pdf,.png,.jpg,.jpeg,.webp'} disabled={busy} onChange={(e) => { void upload(e.target.files); e.target.value = ''; }} /></label>
    </div>
    <p className="quiet-state">Folder access stays in this browser. Excel destinations require a connected folder. Supported: .xlsx, PDF, PNG, JPEG and WebP. Other file types are skipped.</p>
    {!supportsLocalFolder() && <p role="status">Open this workspace in Chrome or Edge to update local Excel files.</p>}
    <div className="accounts-sources">{sources.map((source) => {
      const eligible = source.files.filter((f) => discovery ? /\.xlsx$/i.test(f.path) : /\.(pdf|png|jpe?g|webp)$/i.test(f.path));
      if (!eligible.length) return null;
      return <details key={source.id} open={sources.length < 4}><summary>{source.label} Â· {eligible.length} files Â· {source.writable ? 'Local folder' : 'Uploaded'}</summary>
        {source.writable && <div className="accounts-toolbar"><button className="button button-ghost" disabled={busy} onClick={() => user && void action(() => refreshFolder(tenant,source,user.csrf_token))}>Refresh folder</button>
          <button className="button button-ghost" disabled={busy} onClick={() => user && void action(() => chooseFolder(tenant,user.csrf_token,source))}>Reconnect folder</button></div>}
        <div className="accounts-file-list">{eligible.map((file) => <label key={file.id}><input type="checkbox" checked={selected.includes(file.id)} onChange={(e) => setSelected((old) => e.target.checked ? [...old,file.id] : old.filter((id) => id !== file.id))} />{file.path}</label>)}</div>
      </details>;
    })}</div>
    {!sources.length && <p className="quiet-state">Connect a folder to begin. For the first test, select the synthetic mock-workspace folder.</p>}
    <details className="accounts-config"><summary>Run configuration</summary><div className="accounts-field-grid">
      {discovery ? <><label>Discovery depth<select value={discoveryDepth} onChange={(e) => setDiscoveryDepth(e.target.value)}><option value="business_mappings">Structures and business mappings</option><option value="reference_data">Structures and reference data</option><option value="structure">Structures only</option></select></label>
        <label>Discovery run<select value={refreshMode} onChange={(e) => setRefreshMode(e.target.value)}><option value="initial">Initial discovery</option><option value="refresh">Refresh discovery</option></select></label>
        <label>File limit<input type="number" min="1" max="1000" value={maxFiles} onChange={(e) => setMaxFiles(Number(e.target.value))} /></label></> : <>
        <label>Input types<select value={inputFormat} onChange={(e) => setInputFormat(e.target.value)}><option value="mixed">PDFs and images</option><option value="pdf">PDFs</option><option value="image">Images</option></select></label>
        <label>Review policy<select disabled={outputMode==='tally_in_place'} value={outputMode==='tally_in_place'?'all_outputs':reviewMode} onChange={(e) => setReviewMode(e.target.value)}><option value="all_outputs">Approve every output</option><option value="only_exceptions">Only exceptions</option></select></label>
        <label>Output platform<select value={outputMode} onChange={e=>setOutputMode(e.target.value)}><option value="excel_in_place">Excel · update existing sheets</option><option value="tally_in_place">Tally · purchase vouchers</option></select></label>
        {outputMode==='tally_in_place'?<p role="status">{nativeCatalog?.ready&&nativeCatalog.config.tally?`Confirmed Tally company: ${nativeCatalog.config.tally.company}`:'Confirm Tally company, ledgers and voucher types in Source discovery first.'}</p>:
        <label>Confirmed sources<select value={catalogId} onChange={(e) => setCatalogId(e.target.value)}><option value="">Run source discovery first</option>{catalogs.map((c) => <option key={c.id} value={c.id}>{new Date(c.confirmed_at).toLocaleString()} Â· {c.catalog.sheets.length} sheets</option>)}</select></label>}
        {outputMode!=='tally_in_place'&&<fieldset><legend>Reference checks</legend>{['vendor_match','duplicate','totals','cost_codes'].map((check) => <label key={check}><input type="checkbox" checked={checks.includes(check)} onChange={(e) => setChecks((old) => e.target.checked ? [...old,check] : old.filter((v) => v !== check))} />{check.replaceAll('_',' ')}</label>)}</fieldset>}
      </>}
    </div></details>
    {error && <p role="alert" className="form-message">{error}</p>}
    <button className="button button-primary" disabled={busy || workflow.status !== 'active' || !selected.length || (!discovery && (outputMode==='tally_in_place'? !nativeCatalog?.ready||!nativeCatalog.config.tally : !catalogId))} onClick={() => void launch()}>{busy ? 'Working…' : `Run ${workflow.name.toLowerCase()}`}</button>
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
        if (!latest) { navigate(`/${routeSlug}/workflows/${workflow.id}`); return; }
        const launched=await api<Run>(`/api/tenants/${tenant}/discovery/runs`,{method:'POST',body:JSON.stringify({device_id:latest.device_id,config:latest.config,request_key:crypto.randomUUID()})},user.csrf_token);
        navigate(`/${routeSlug}/tasks/${launched.task_id}`); return;
      }
      const [sources,catalogs] = await Promise.all([api<Source[]>(base+'/sources'),api<SavedCatalog[]>(base+'/catalogs')]);
      let target:{output_mode?:string;catalog_id?:string;discovery_id?:string}={};
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
      // Refresh the selected local source before recognition so newly changed
      // bytes cannot silently be treated as the earlier snapshot.
      const selectedSources = sources.filter((source) => source.files.some((file) => selections.includes(`${source.id}:${file.path}`)));
      const refreshed = [];
      for (const source of selectedSources) refreshed.push(source.writable ? await refreshFolder(tenant,source,user.csrf_token) : source);
      const files = refreshed.flatMap((source) => source.files.filter((file) => selections.includes(`${source.id}:${file.path}`) &&
        (discovery ? /\.xlsx$/i.test(file.path) : /\.(pdf|png|jpe?g|webp)$/i.test(file.path))).map((file) => file.id));
      if (!files.length) throw new Error('Your saved selection is unavailable. Open workflow details to select files.');
      const loaded = await api<Run>(base+'/runs', {method:'POST',body:JSON.stringify({
        key:workflow.key,request_key:crypto.randomUUID(),file_ids:files,catalog_id:tally ? null : target.catalog_id??catalogs[0].id,
        config:tally?{output_mode:'tally_in_place',discovery_id:target.discovery_id}:{output_mode:'excel_in_place'},
      })},user.csrf_token);
      navigate(`/${routeSlug}/tasks/${loaded.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Open workflow details to reconnect your folder.'); }
    finally { setBusy(false); }
  }
  return <div><button className="button button-primary" disabled={busy} onClick={() => void run()}>{busy ? 'Startingâ€¦' : 'Run workflow'}</button>
    {error && <p role="alert" className="form-message">{error}</p>}</div>;
}

export function AccountsLaunch(props:{tenant:string;routeSlug:string;workflow:Workflow}) {
  return presentationFor(props.workflow)==='accounts-discovery'?<DiscoveryLaunch {...props}/>:<LegacyAccountsLaunch {...props}/>;
}
