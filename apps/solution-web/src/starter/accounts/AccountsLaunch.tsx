import { RunSettings, type RunSettingsProps } from "../workflows/RunSettings";
import { Spinner } from '../components/Feedback';
import { BillFileSelection } from './BillFileSelection';
import { restoreSelection, reconcileSelection, selectionKeys } from './fileSelection';
import { destinationPreference } from '../desktop/destinationPCs';
import type { DestinationPCState } from '../desktop/DestinationPC';
import { DiscoveryLaunch } from './Discovery';
import { presentationFor } from '../workflows/presentation';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type Workflow } from '../api';
import { useAuth } from '../contexts/AuthContext';
import { chooseFolder, refreshFolder, supportsLocalFolder } from './localFiles';
import type { Run, Source, SavedCatalog } from './types';

interface NativeCatalog { id:string; ready:boolean; device_id:string; config:{tally:{company?:string}|null};catalog?:{excel_catalog_id?:string;format_version?:string;sources:{tool:string;snapshot?:{companies?:{company:string;company_guid:string}[]}}[]} }
const discoveredCompanies = (catalog:NativeCatalog|null) => catalog?.catalog?.sources.flatMap(s=>s.tool==='tally' ? s.snapshot?.companies ?? [] : []) ?? [];

function BillEntryLaunch({ tenant, routeSlug, workflow, onConfigChange, destination, settings }: RunSettingsProps & { routeSlug: string; destination?: DestinationPCState }) {
  const { user } = useAuth(); const navigate = useNavigate();
  const [sources, setSources] = useState<Source[]>([]);
  const [catalogs, setCatalogs] = useState<SavedCatalog[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [catalogId, setCatalogId] = useState('');
  const outputMode = String(workflow.config_values.output_mode ?? 'excel_in_place');
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'failed'>('loading');
  const loaded = loadState === 'ready';
  const [loadedNativeCatalog,setNativeCatalog] = useState<NativeCatalog|null>(null);
  const companyMode = workflow.config_values.company_mode === 'locked' ? 'locked' : 'infer';
  const nativeCatalog = loadedNativeCatalog?.device_id === destination?.deviceId ? loadedNativeCatalog : null;
  const destinationCatalogs = catalogs.filter(catalog => catalog.id === nativeCatalog?.catalog?.excel_catalog_id);
  const destinationCatalogId = destinationCatalogs.some(catalog => catalog.id === catalogId) ? catalogId : destinationCatalogs[0]?.id ?? '';
  const lockedCompanyGuid = String(workflow.config_values.locked_company_guid ?? discoveredCompanies(nativeCatalog)[0]?.company_guid ?? '');
  const [nativeError, setNativeError] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const inputFormat = String(workflow.config_values.input_format ?? 'mixed');
  const reviewMode = String(workflow.config_values.review_mode ?? 'all_outputs');
  const [checks, setChecks] = useState(['vendor_match','duplicate','totals','cost_codes']);
  const base = `/api/tenants/${tenant}/accounts`;
  const preferences = `${tenant}:${workflow.key}:selections:v1`;
  useEffect(() => {
    let active = true;
    setNativeCatalog(null); setNativeError('');
    if (destination?.deviceId && destination.available) {
      void api<NativeCatalog|null>(`/api/tenants/${tenant}/discovery/latest?device_id=${encodeURIComponent(destination.deviceId)}`)
        .then(catalog => { if (active) setNativeCatalog(catalog); })
        .catch((e: Error) => { if (active) setNativeError(e.message); });
    }
    return () => { active = false; };
  }, [tenant, destination?.deviceId, destination?.available]);

  async function refresh() {
    const [loadedSources, loadedCatalogs] = await Promise.all([api<Source[]>(base + '/sources'), api<SavedCatalog[]>(base + '/catalogs')]);
    setSources(loadedSources); setCatalogs(loadedCatalogs.filter(c=>c.catalog.sheets.some(s=>s.role==='destination')));
    setCatalogId((current) => current || loadedCatalogs[0]?.id || '');
    if (loaded) setSelected(current => reconcileSelection(sources, loadedSources, current));
    else {
      let raw: string | null = null;
      try { raw = localStorage.getItem(preferences); } catch { /* Storage may be unavailable. */ }
      setSelected(restoreSelection(loadedSources, raw));
    }
    setLoadState('ready');
  }
  useEffect(() => { let active = true;
    void Promise.all([api<Source[]>(base + '/sources'), api<SavedCatalog[]>(base + '/catalogs')]).then(([ss, cc]) => {
      if (!active) return;
      const destinations=cc.filter(c=>c.catalog.sheets.some(s=>s.role==='destination'));
      setSources(ss); setCatalogs(destinations); setCatalogId(destinations[0]?.id ?? '');
      let raw: string | null = null;
      try { raw = localStorage.getItem(preferences); } catch { /* Storage may be unavailable. */ }
      setSelected(restoreSelection(ss, raw)); setLoadState('ready');
    }).catch((e: Error) => { if (active) { setError(e.message); setLoadState('failed'); } });
    return () => { active = false; };
  }, [base, preferences]);

  useEffect(() => {
    if (!loaded) return;
    try { localStorage.setItem(preferences, JSON.stringify(selectionKeys(sources, selected))); }
    catch { /* Browser preference storage must not block a run. */ }
  }, [sources, selected, loaded, preferences]);

  async function action(work?: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { if (work) await work(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Could not complete this action.'); }
    finally { setBusy(false); }
  }
  async function upload(files: FileList | null) {
    if (!files?.length || !user) return;
    await action(async () => {
      const form = new FormData(); form.append('paths', JSON.stringify(Array.from(files, (f) => f.name)));
      Array.from(files).forEach((f) => form.append('files', f));
      await api(base + '/sources', { method: 'POST', body: form }, user.csrf_token);
    });
  }
  async function launch() {
    if (!user || busy || !destination?.available) return;
    setBusy(true); setError('');
    try {
      try { localStorage.setItem(`${tenant}:bill-entry:target:v1`,JSON.stringify({device_id:destination?.deviceId,output_mode:outputMode,catalog_id:destinationCatalogId,discovery_id:nativeCatalog?.id,company_mode:companyMode,locked_company_guid:companyMode==='locked'?lockedCompanyGuid:null})); } catch { /* Setup remains available if browser storage is disabled. */ }
      const run = await api<Run>(base + '/runs', { method: 'POST', body: JSON.stringify({
        key: workflow.key, request_key: crypto.randomUUID(), file_ids: selected, destination_device_id: destination?.deviceId,
        catalog_id: outputMode==='tally_in_place' ? null : destinationCatalogId,
        config: { ...workflow.config_values, input_format: inputFormat, review_mode: reviewMode, output_mode: outputMode, checks, ...(outputMode==='tally_in_place'?{discovery_id:nativeCatalog?.id,company_mode:companyMode,locked_company_guid:companyMode==='locked'?lockedCompanyGuid:null}:{}) },
      }) }, user.csrf_token);
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start workflow.'); }
    finally { setBusy(false); }
  }
  return <section className="accounts-panel bill-launch" aria-label="Run workflow">
    <div className="section-heading"><div><h3>Enter bills</h3>
      <p>Read selected bills, resolve exceptions, and verify saves in your configured destination.</p></div></div>
    <BillFileSelection sources={sources} selected={selected} loading={loadState === 'loading'} loadFailed={loadState === 'failed'} onRetry={() => void action()} busy={busy} canConnect={supportsLocalFolder()}
      onSelect={setSelected} onUpload={files => void upload(files)}
      onConnect={() => user && void action(() => chooseFolder(tenant,user.csrf_token))}
      onRefresh={source => user && void action(() => refreshFolder(tenant,source,user.csrf_token))}
      onReconnect={source => user && void action(() => chooseFolder(tenant,user.csrf_token,source))} />
    <details className="accounts-config"><summary>Destination and checks</summary><div className="accounts-field-grid">
        {outputMode==='tally_in_place'?<p role="status">{nativeCatalog?.ready&&discoveredCompanies(nativeCatalog).length?`${discoveredCompanies(nativeCatalog).length} discovered companies available`:`Run and confirm complete Tally Source Discovery on ${destination?.name || 'the selected PC'} first.`}</p>:
        <label>Confirmed sources<select aria-label="Confirmed sources" value={destinationCatalogId} onChange={(e) => setCatalogId(e.target.value)}><option value="">Run source discovery first</option>{destinationCatalogs.map((c) => <option key={c.id} value={c.id}>{new Date(c.confirmed_at).toLocaleString()} · {c.catalog.sheets.length} sheets</option>)}</select></label>}
        {outputMode==='tally_in_place'&&<><label>Company selection<select aria-label="Company selection" value={companyMode} onChange={e=>onConfigChange?.({...workflow.config_values,company_mode:e.target.value})}><option value="infer">Infer from each bill · any discovered company</option><option value="locked">Use one company for this run</option></select></label>{companyMode==='locked'&&<label>Company for all bills<select aria-label="Company for all bills" value={lockedCompanyGuid} onChange={e=>onConfigChange?.({...workflow.config_values,locked_company_guid:e.target.value})}><option value="">Choose a company</option>{discoveredCompanies(nativeCatalog).map(c=><option key={c.company_guid} value={c.company_guid}>{c.company}</option>)}</select></label>}</>}
        {outputMode!=='tally_in_place'&&<fieldset><legend>Reference checks</legend>{['vendor_match','duplicate','totals','cost_codes'].map((check) => <label key={check}><input type="checkbox" checked={checks.includes(check)} onChange={(e) => setChecks((old) => e.target.checked ? [...old,check] : old.filter((v) => v !== check))} />{check.replaceAll('_',' ')}</label>)}</fieldset>}
    </div></details>
    <RunSettings tenant={tenant} workflow={workflow} onConfigChange={onConfigChange} settings={settings} exclude={["company_mode", "locked_company_guid"]} busy={busy} />
    {!selected.length && <p className="quiet-state">Select at least one bill to run.</p>}
    {workflow.status !== "active" && <p className="quiet-state">This workflow is unavailable for new runs.</p>}
    {nativeError && <p role="alert" className="form-message">{nativeError}</p>}
    {error && <p role="alert" className="form-message">{error}</p>}
    <button className="button button-primary" disabled={!loaded || !destination?.available || busy || workflow.status !== 'active' || !selected.length || (outputMode==='tally_in_place'? !nativeCatalog?.ready||!discoveredCompanies(nativeCatalog).length||(companyMode==='locked'&&!discoveredCompanies(nativeCatalog).some(company=>company.company_guid===lockedCompanyGuid)) : !destinationCatalogId || !nativeCatalog?.ready)} onClick={() => void launch()}>{busy && <Spinner />}{busy ? 'Working…' : `Run ${workflow.name.toLowerCase()}`}</button>
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
      let target:{device_id?:string;output_mode?:string;catalog_id?:string;discovery_id?:string;company_mode?:string;locked_company_guid?:string|null}={};
      try { target=JSON.parse(localStorage.getItem(`${tenant}:bill-entry:target:v1`)??'{}') as typeof target; } catch { /* Setup is authoritative. */ }
      let selectedPC: unknown = null;
      try { selectedPC = JSON.parse(localStorage.getItem(destinationPreference(tenant, user.id, workflow.key)) ?? 'null'); }
      catch { /* Unknown preferences require an explicit destination choice. */ }
      if (!target.device_id || selectedPC !== target.device_id) { navigate(`/${routeSlug}/workflows/${workflow.id}`); return; }
      if (target.output_mode !== workflow.config_values.output_mode) { navigate(`/${routeSlug}/workflows/${workflow.id}`); return; }
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
          api<NativeCatalog|null>(`/api/tenants/${tenant}/discovery/latest?device_id=${encodeURIComponent(target.device_id)}`),
        ]);
        const identities=(catalog:NativeCatalog|null)=>discoveredCompanies(catalog).map(c=>c.company_guid).sort().join('|');
        if (!latest?.ready || !identities(latest) || latest.device_id!==target.device_id || latest.device_id!==selectedTarget.device_id || identities(latest)!==identities(selectedTarget)) {
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
        (discovery ? /\.xlsx$/i.test(file.path) : /\.(pdf|png|jpe?g|webp)$/i.test(file.path))).map((file) => file.id));
      if (!files.length) throw new Error('Your saved selection is unavailable. Open workflow details to select files.');
      const loaded = await api<Run>(base+'/runs', {method:'POST',body:JSON.stringify({
        key:workflow.key,request_key:crypto.randomUUID(),destination_device_id:target.device_id,file_ids:files,catalog_id:tally ? null : target.catalog_id??catalogs[0].id,
        config:tally?{...workflow.config_values,output_mode:'tally_in_place',discovery_id:target.discovery_id,company_mode:target.company_mode??'infer',locked_company_guid:target.locked_company_guid??null}:{...workflow.config_values,output_mode:'excel_in_place'},
      })},user.csrf_token);
      navigate(`/${routeSlug}/tasks/${loaded.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Open workflow details to reconnect your folder.'); }
    finally { setBusy(false); }
  }
  return <div><button className="button button-primary" disabled={busy} onClick={() => void run()}>{busy && <Spinner />}{busy ? 'Starting…' : 'Run workflow'}</button>
    {error && <p role="alert" className="form-message">{error}</p>}</div>;
}

export function AccountsLaunch(props:RunSettingsProps & {routeSlug:string;destination?: DestinationPCState}) {
  return presentationFor(props.workflow)==='accounts-discovery'?<DiscoveryLaunch {...props}/>:<BillEntryLaunch {...props}/>;
}
