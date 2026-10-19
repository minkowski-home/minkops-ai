import {useEffect, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {api} from '../api';
import {useAuth} from '../contexts/AuthContext';
import {RunSettings, type RunSettingsProps} from '../workflows/RunSettings';
import type {DestinationPCState} from '../desktop/DestinationPC';
import {downloadFile} from '../desktop/bridge';
import {chooseFolder, refreshFolder, supportsLocalFolder} from './localFiles';
import type {Run, Source} from './types';
import {restoreSelection,selectionKeys} from './fileSelection';

type Company = {company:string;company_guid:string;statement_options:{banks:{name:string;guid:string}[];voucher_types:{name:string;guid:string;base:string}[]}};
interface Discovery {id:string;device_id:string;ready:boolean;catalog?:{sources:{tool:string;snapshot?:{companies?:Company[]}}[]}}
const STATEMENT_FILES=/\.(csv|xlsx)$/i;
const money=(cents:number)=>new Intl.NumberFormat('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(cents/100);
const preference=(tenant:string,user:string)=>`${tenant}:${user}:statement-entry:setup:v1`;
interface SavedSetup {deviceId:string;files:string[];banks:Record<string,string>;types:Record<string,Record<string,string>>}
function savedSetup(tenant:string,user:string):SavedSetup|null {
  try {const saved=JSON.parse(localStorage.getItem(preference(tenant,user))??'null') as SavedSetup|null;
    return saved&&typeof saved.deviceId==='string'&&Array.isArray(saved.files)&&saved.banks&&saved.types?saved:null;
  } catch {return null;}
}

export async function quickStatementRun(tenant:string,workflow:RunSettingsProps['workflow'],user:{id:string;csrf_token:string},deviceId:string):Promise<Run|null> {
  const saved=savedSetup(tenant,user.id);if(!saved||saved.deviceId!==deviceId)return null;
  const base=`/api/tenants/${tenant}/accounts`;
  const [sources,discovery]=await Promise.all([api<Source[]>(base+'/sources'),api<Discovery|null>(`/api/tenants/${tenant}/discovery/latest?device_id=${encodeURIComponent(deviceId)}`)]);
  if(!discovery?.ready)return null;
  const selected=restoreSelection(sources,JSON.stringify(saved.files),STATEMENT_FILES);
  const refreshed=await Promise.all(sources.filter(s=>s.files.some(f=>selected.includes(f.id))).map(s=>s.writable?refreshFolder(tenant,s,user.csrf_token):Promise.resolve(s)));
  const ids=restoreSelection(refreshed,JSON.stringify(saved.files),STATEMENT_FILES);if(!ids.length)return null;
  return api<Run>(base+'/runs',{method:'POST',body:JSON.stringify({key:workflow.key,request_key:crypto.randomUUID(),file_ids:ids,destination_device_id:deviceId,
    config:{...workflow.config_values,discovery_id:discovery.id,bank_ledgers:saved.banks,voucher_types:saved.types}})},user.csrf_token);
}

export function StatementLaunch(props:RunSettingsProps & {routeSlug:string;destination?:DestinationPCState}) {
  const {tenant,workflow,destination}=props, {user}=useAuth(), navigate=useNavigate();
  const userId=user?.id;
  const [sources,setSources]=useState<Source[]>([]),[selected,setSelected]=useState<string[]>([]);
  const [discovery,setDiscovery]=useState<Discovery|null>(null),[banks,setBanks]=useState<Record<string,string>>({});
  const [types,setTypes]=useState<Record<string,Record<string,string>>>({});
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const base=`/api/tenants/${tenant}/accounts`;
  useEffect(()=>{
    let active=true; setDiscovery(null);
    void Promise.all([api<Source[]>(base+'/sources'),destination?.deviceId?api<Discovery|null>(`/api/tenants/${tenant}/discovery/latest?device_id=${encodeURIComponent(destination.deviceId)}`):Promise.resolve(null)])
      .then(([files,found])=>{if(active){setSources(files);setDiscovery(found);const saved=userId?savedSetup(tenant,userId):null;
        if(saved&&saved.deviceId===destination?.deviceId){setSelected(restoreSelection(files,JSON.stringify(saved.files),STATEMENT_FILES));setBanks(saved.banks);setTypes(saved.types);}}})
      .catch((e:Error)=>{if(active)setError(e.message);});
    return()=>{active=false;};
  },[base,tenant,destination?.deviceId,userId]);
  const companies=discovery?.catalog?.sources.flatMap(s=>s.tool==='tally'?s.snapshot?.companies??[]:[])??[];
  async function action(work:()=>Promise<unknown>){
    if(!user)return;setBusy(true);setError('');
    try{await work();setSources(await api<Source[]>(base+'/sources'));}
    catch(e){setError(e instanceof Error?e.message:'Could not complete this action.');}finally{setBusy(false);}
  }
  async function launch(){
    if(!user||!discovery)return;setBusy(true);setError('');
    try{
      const config={...workflow.config_values,discovery_id:discovery.id,bank_ledgers:banks,voucher_types:types};
      const run=await api<Run>(base+'/runs',{method:'POST',body:JSON.stringify({key:workflow.key,request_key:crypto.randomUUID(),
        file_ids:selected,destination_device_id:destination?.deviceId,config})},user.csrf_token);
      try {localStorage.setItem(preference(tenant,user.id),JSON.stringify({deviceId:destination?.deviceId,files:selectionKeys(sources,selected,STATEMENT_FILES),banks,types}));} catch {/* Preferences do not affect authorization. */}
      navigate(`/${props.routeSlug}/tasks/${run.task_id}`);
    }catch(e){setError(e instanceof Error?e.message:'Could not start statement entry.');}finally{setBusy(false);}
  }
  return <section className="accounts-panel" aria-label="Statement entry setup">
    <h3>Enter bank statements</h3><p>Add a Branch column to your CSV or XLSX statement. Minkops checks the running balances and matches each branch against Source Discovery.</p>
    <div className="accounts-toolbar"><label className="button button-ghost">Upload statements<input aria-label="Upload statements" type="file" multiple accept=".csv,.xlsx" disabled={busy} onChange={e=>{
      const files=Array.from(e.target.files??[]);if(!files.length)return;
      void action(async()=>{const form=new FormData();form.append('paths',JSON.stringify(files.map(f=>f.name)));files.forEach(f=>form.append('files',f));await api(base+'/sources',{method:'POST',body:form},user!.csrf_token);});
    }}/></label>{supportsLocalFolder()&&<button className="button button-ghost" disabled={busy} onClick={()=>void action(()=>chooseFolder(tenant,user!.csrf_token))}>Connect folder</button>}</div>
    {sources.filter(s=>s.files.some(f=>/\.(csv|xlsx)$/i.test(f.path))).map(source=><details key={source.id} className="accounts-sources" open>
      <summary>{source.label}</summary>{source.writable&&<button className="button button-ghost" disabled={busy} onClick={()=>void action(()=>refreshFolder(tenant,source,user!.csrf_token))}>Refresh folder</button>}
      {source.files.filter(f=>/\.(csv|xlsx)$/i.test(f.path)).map(file=><label key={file.id} className="accounts-check"><input type="checkbox" disabled={busy} checked={selected.includes(file.id)}
        onChange={e=>setSelected(old=>e.target.checked?[...old,file.id]:old.filter(id=>id!==file.id))}/>{file.path}</label>)}
    </details>)}
    {!discovery?.ready&&<p role="status">Run and confirm complete Source Discovery on the selected PC first.</p>}
    <fieldset><legend>Bank destinations</legend><p>Select a bank ledger for each company this statement can use.</p>{companies.map(company=>{
      const choices=company.statement_options;
      return <div className="accounts-field-grid" key={company.company_guid}><label>Bank ledger · {company.company}<select value={banks[company.company_guid]??''} aria-label={`Bank ledger for ${company.company}`}
        onChange={e=>setBanks(old=>{const next={...old};if(e.target.value)next[company.company_guid]=e.target.value;else delete next[company.company_guid];return next;})}>
        <option value="">Exclude this company</option>{(choices?.banks??[]).map(m=><option key={m.guid||m.name} value={m.name}>{m.name}</option>)}</select></label>
        {['payment','receipt'].map(base=>{const candidates=(choices?.voucher_types??[]).filter(m=>m.base===base);
          return candidates.length>1?<label key={base}>{base==='payment'?'Payment':'Receipt'} type · {company.company}<select value={types[company.company_guid]?.[base]??''}
            onChange={e=>setTypes(old=>({...old,[company.company_guid]:{...old[company.company_guid],[base]:e.target.value}}))}><option value="">Choose a voucher type</option>{candidates.map(m=><option key={m.guid} value={m.guid}>{m.name}</option>)}</select></label>:null;})}
      </div>;
    })}</fieldset>
    <RunSettings {...props} busy={busy}/>
    {error&&<p role="alert">{error}</p>}
    <button className="button button-primary" disabled={busy||!destination?.available||!discovery?.ready||!selected.length||!Object.keys(banks).length||!String(workflow.config_values.other_side_ledger??'').trim()||workflow.status!=='active'} onClick={()=>void launch()}>{busy?'Working…':'Check statements'}</button>
  </section>;
}

interface StatementRow {source_file:string;sheet:string;row:number;branch?:string;date?:string;reference?:string;amount_cents?:number;balance_cents?:number;company?:string;status:string;code?:string;reason?:string;save_hold?:boolean}
export function StatementReview({tenant,run,onChanged,blocked}:{tenant:string;run:Run;onChanged:(run:Run)=>void;blocked:boolean}){
  const {user}=useAuth(),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [visible,setVisible]=useState(100);
  const rows=(run.result as unknown as {records?:StatementRow[]}|null)?.records??[];
  const groups=[...new Set(rows.map(r=>r.branch??'Unresolved'))].map(branch=>{
    const selected=rows.filter(r=>(r.branch??'Unresolved')===branch);
    return {branch,count:selected.length,payment:-selected.reduce((n,r)=>n+Math.min(r.amount_cents??0,0),0),receipt:selected.reduce((n,r)=>n+Math.max(r.amount_cents??0,0),0),
      dates:selected.flatMap(r=>r.date?[r.date]:[]).sort(),held:selected.filter(r=>r.code).length};
  });
  const settled=rows.filter(r=>['saved','duplicate'].includes(r.status));
  async function act(action:string){if(!user)return;setBusy(true);setError('');try{
    onChanged(await api<Run>(`/api/tenants/${tenant}/accounts/runs/${run.id}/approve`,{method:'POST',body:JSON.stringify({result:{action}})},user.csrf_token));
  }catch(e){setError(e instanceof Error?e.message:'Could not complete this action.');}finally{setBusy(false);}}
  return <section className="accounts-panel" aria-label="Statement preview"><h3>Statement preview</h3>
    <p>{rows.length} rows · {settled.filter(r=>r.status==='saved').length} saved · {settled.filter(r=>r.status==='duplicate').length} already in Tally</p>
    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard access to the horizontally scrolling data region. */}
    <div className="statement-summary" role="region" aria-label="Statement branch totals" tabIndex={0}><table><thead><tr><th>Branch</th><th>Rows</th><th>Payments</th><th>Receipts</th><th>Date range</th><th>Checks</th></tr></thead><tbody>{groups.map(g=><tr key={g.branch}><td>{g.branch}</td><td>{g.count}</td><td>{money(g.payment)}</td><td>{money(g.receipt)}</td><td>{g.dates[0]} – {g.dates.at(-1)}</td><td>{g.held?`${g.held} exceptions`:'Balances verified'}</td></tr>)}</tbody></table></div>
    <div className="accounts-toolbar"><button className="button button-ghost" disabled={busy||!run.result||!['review','completed','failed','stopped'].includes(run.state)} onClick={()=>{
      setBusy(true);void downloadFile(`/api/tenants/${tenant}/accounts/runs/${run.id}/statement-exceptions.csv`,`statement-exceptions-${run.id}.csv`)
        .catch(()=>setError('Could not export exceptions.')).finally(()=>setBusy(false));}}>Export CSV</button>
      {run.state==='review'&&run.actor_id===user?.id&&<>
        {rows.some(r=>r.status==='ready')&&<button className="button button-primary" disabled={busy||blocked} onClick={()=>void act('write_ready')}>Write ready rows</button>}
        {rows.some(r=>r.save_hold)&&<button className="button button-ghost" disabled={busy||blocked} onClick={()=>void act('retry_saves')}>Retry save checks</button>}
        {rows.some(r=>!['saved','duplicate','rejected'].includes(r.status))&&<button className="button button-ghost" disabled={busy||blocked} onClick={()=>void act('nothing')}>Do nothing with remaining rows</button>}
      </>}
    </div>
    {settled.length>0&&<details><summary>{settled.length} verified rows</summary>{settled.slice(0,visible).map((r,i)=><p key={i}>{r.date} · {r.reference} · {money(r.amount_cents??0)} · {r.company}</p>)}</details>}
    {rows.filter(r=>!['saved','duplicate'].includes(r.status)).sort((a,b)=>Number(Boolean(b.code))-Number(Boolean(a.code))).slice(0,visible).map((r,i)=><article className="accounts-bill" key={i}><h4>{r.source_file} · {r.sheet&&`${r.sheet} · `}row {r.row}</h4>
      <p>{r.branch||'Unresolved branch'} · {r.date} · {r.reference} · {r.amount_cents==null?'Unconfirmed amount':money(r.amount_cents)} · {r.company}</p>
      <p>{r.reason??(r.status==='ready'?'Balances verified. Ready to save.':r.status==='writing'?'Saving and verifying in Tally.':r.status==='rejected'?'Left for manual handling.':'Needs attention.')}</p></article>)}
    {rows.length>visible&&<button className="button button-ghost" onClick={()=>setVisible(old=>old+100)}>Show more rows</button>}
    {run.state==='writing'&&<p role="status">Saving and verifying one voucher at a time. Keep Minkops and Tally running on your PC.</p>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
