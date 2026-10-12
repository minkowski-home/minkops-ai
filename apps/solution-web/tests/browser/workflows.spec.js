/* global URL, Buffer, document, window, localStorage, console, Storage */
import { test } from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
test('Bill entry and contextual PC checks preserve defaults, selections and safety', async ({ page, context }, testInfo) => {
let member=false, failDefaults=false, failUpload=false, failRun=false, failLoad=false;
let sources=[{id:'upload',label:'Synthetic uploads',writable:false,files:[{id:'a',path:'invoice-a.PDF',sha256:'a'},{id:'b',path:'nested/receipt-b.jpg',sha256:'b'},{id:'unsupported',path:'notes.txt',sha256:'x'}]},{id:'folder',label:'Synthetic PC folder',writable:true,files:[{id:'c',path:'invoice-c.pdf',sha256:'c'},{id:'d',path:'long/nested/path/'+ 'long-name-'.repeat(15)+'.webp',sha256:'d'}]}];

const schema=JSON.parse(fs.readFileSync(new URL('../../../../employees/accounts-desk/workflows/bill-entry/tenant-config.schema.json', import.meta.url)));
schema.properties.output_mode['x-enabled-options']=['tally_in_place'];
let defaults={input_format:'mixed',output_mode:'tally_in_place',review_mode:'only_exceptions',company_mode:'infer'};
const workflows=()=>[{id:'bill',key:'bill-entry',name:'Bill entry',description:'Enter synthetic bills with approved writes.',status:'active',employee_ids:[],config_schema:schema,config_values:defaults,config_version:1,presentation:'accounts-bill'}];
const catalog={id:'discovery',ready:true,device_id:'pc',config:{tally:{}},catalog:{sources:[{tool:'tally',snapshot:{companies:[{company:'Synthetic Company',company_guid:'company'}]}}]}};
const jobs=[], runs=[], patches=[], errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,r=>r.fulfill({body:'',contentType:'text/css'}));
await context.route('**/api/**',async r=>{
 const req=r.request(),path=new URL(req.url()).pathname,method=req.method(); let body=null,status=200;
 if(path==='/api/auth/session')body={id:'user',name:'Synthetic QA',email:'qa@example.test',is_platform_admin:false,memberships:[{slug:'mock-tenant',name:'Synthetic QA',role:member?'member':'admin'}],csrf_token:'synthetic-csrf'};
 else if(path.endsWith('/workspace'))body={tenant:{slug:'mock-tenant',name:'Synthetic QA'},can_edit:!member,employees:[],workflows:workflows(),tasks:[]};
 else if(path.endsWith('/accounts/sources')&&method==='GET'){body=sources;if(failLoad){status=503;body={detail:'Synthetic source load failed'};}}
 else if(path.endsWith('/accounts/sources')&&method==='POST'){
  if(failUpload){status=400;body={detail:'Synthetic upload failed'};}
  else {sources=[...sources,{id:'added',label:'New upload',writable:false,files:[{id:'new',path:'new.pdf',sha256:'new'}]}];body=sources.at(-1);}
 }
 else if(path.endsWith('/accounts/catalogs'))body=[{id:'excel',confirmed_at:'2026-10-12',catalog:{sheets:[{role:'destination'}]}}];
 else if(path.endsWith('/discovery/latest')||path.endsWith('/discovery/runs/discovery'))body=catalog;
 else if(path.endsWith('/workflows/bill')&&method==='PATCH'){assert.equal(req.headers()['x-csrf-token'],'synthetic-csrf');patches.push(req.postDataJSON());if(failDefaults){status=400;body={detail:'Synthetic default save failed'};}else{defaults=req.postDataJSON().config_values;body={};}}
 else if(path.endsWith('/accounts/runs')&&method==='POST'){runs.push(req.postDataJSON());assert.equal(req.headers()['x-csrf-token'],'synthetic-csrf');if(failRun){status=400;body={detail:'Synthetic run failed'};}else body={task_id:'run-task'};}
 else if(path.endsWith('/desktop/devices'))body=[{id:'pc',name:'QA PC',owner_id:'user',revoked_at:null,expires_at:'2099-01-01',last_seen_at:new Date().toISOString()},{id:'offline',name:'Offline PC',owner_id:'user',revoked_at:null,expires_at:'2099-01-01',last_seen_at:null},{id:'expired',name:'Expired PC',owner_id:'user',revoked_at:null,expires_at:'2000-01-01',last_seen_at:null},{id:'other',name:'Other owner PC',owner_id:'other',revoked_at:null,expires_at:'2099-01-01',last_seen_at:null}];
 else if(path.endsWith('/desktop/sources'))body=[{source_id:'folder',device_id:'pc'}];
 else if(path.endsWith('/desktop/jobs')&&method==='POST'&&req.postDataJSON().operation==='files.refresh'){sources=sources.map(source=>source.id==='folder'?{...source,files:source.files.map(file=>({...file,id:file.id+'-refreshed'})).concat([{id:'fresh',path:'fresh.pdf',sha256:'fresh'}])}:source);body={id:'refresh-job',state:'completed'};}
 else if(path.endsWith('/desktop/jobs')&&method==='POST'){jobs.push(req.postDataJSON());assert.equal(req.headers()['x-csrf-token'],'synthetic-csrf');body={task_id:'probe-task'};}
 else if(path.endsWith('/run'))body=null;
 else if(path.includes('/tasks/'))body={id:'run-task',title:'Synthetic task',workflow_id:'bill',status:'running',progress:0,summary:'Synthetic task queued',events:[]};
 else {throw new Error(`Unhandled mock ${method} ${path}`);}
 await r.fulfill({status,json:body});
});
const url='http://127.0.0.1:3000/mock-tenant/workflows/bill';
async function open(){await page.goto(url);await page.getByRole('button',{name:'Clear selection',exact:true}).waitFor();await page.getByText('Loading bill files…',{exact:true}).waitFor({state:'hidden'});const picker=page.getByLabel('Destination PC',{exact:true});await picker.waitFor();await picker.selectOption('pc');}

const selection=page.getByRole('region',{name:'Bill files',exact:true});
const checks=()=>selection.getByRole('checkbox');
await open();assert.match(await page.title(),/MinkOps/);assert.equal(await checks().count(),4);assert.equal(await page.getByRole('heading',{name:'Workflow administration',exact:true}).count(),1);assert.equal(await page.getByText('Run configuration',{exact:true}).count(),0);
assert.equal(await page.getByLabel('Bill inputs',{exact:true}).count(),1);
assert.equal(await page.getByText(/Tally runs always/).count(),0);
assert.equal(await page.getByLabel('Review mode',{exact:true}).count(),1);
await checks().nth(0).uncheck();assert.equal(await checks().nth(0).isChecked(),false);
await page.getByRole('button',{name:'Clear selection',exact:true}).click();await page.reload();await page.getByRole('button',{name:'Run bill entry',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Run bill entry',exact:true}).isDisabled(),true);assert.equal(await checks().nth(0).isChecked(),false);
await page.getByLabel('Find a bill').fill('receipt');assert.equal(await checks().count(),1);await page.getByRole('button',{name:'Select results',exact:true}).click();assert.equal(await checks().nth(0).isChecked(),true);
await page.getByLabel('Find a bill').fill('unmatched');assert.equal(await page.getByText('No bills match your search.').count(),1);
await page.getByLabel('Find a bill').fill('');await page.getByRole('button',{name:'Select all',exact:true}).click();assert.equal(await checks().nth(3).isChecked(),true);
await page.getByRole('button',{name:'Clear group',exact:true}).first().click();assert.equal(await checks().nth(0).isChecked(),false);assert.equal(await checks().nth(2).isChecked(),true);
await page.getByRole('button',{name:'Select group',exact:true}).first().click();await checks().nth(0).uncheck();
await page.getByLabel('Upload workflow files').setInputFiles({name:'new.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 synthetic')});await page.waitForFunction(()=>document.body.innerText.includes('of 5 selected'));assert.equal(await checks().nth(0).isChecked(),false);assert.equal(await checks().nth(4).isChecked(),false);
failUpload=true;await page.getByLabel('Upload workflow files').setInputFiles({name:'failed.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic')});await page.getByText('Synthetic upload failed',{exact:true}).waitFor();assert.equal(await checks().nth(4).isChecked(),false);failUpload=false;
// Actual file chooser is keyboard activatable; no exposed native upload widget.
const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Upload files',exact:true}).focus();await page.keyboard.press('Enter');await (await chooser).setFiles([]);
await page.getByLabel('Bill inputs',{exact:true}).selectOption('pdf');await page.getByRole('button',{name:'Save as defaults',exact:true}).click();await page.getByText('Defaults saved. This run keeps your selected options.',{exact:true}).waitFor();assert.equal(patches.at(-1).config_values.input_format,'pdf');
await page.getByLabel('Bill inputs',{exact:true}).selectOption('image');assert.equal(defaults.input_format,'pdf');
failDefaults=true;await page.getByRole('button',{name:'Save as defaults',exact:true}).click();await page.getByText('Synthetic default save failed',{exact:true}).waitFor();assert.equal(defaults.input_format,'pdf');assert.equal(await page.getByLabel('Bill inputs',{exact:true}).inputValue(),'image');failDefaults=false;
await page.getByRole('button',{name:'Reset to defaults',exact:true}).click();assert.equal(await page.getByLabel('Bill inputs',{exact:true}).inputValue(),'pdf');
await page.getByLabel('Bill inputs',{exact:true}).selectOption('image');
await page.getByText('Destination and checks',{exact:true}).click();await page.getByLabel('Company selection',{exact:true}).selectOption('locked');assert.equal(await page.getByLabel('Company for all bills',{exact:true}).inputValue(),'company');
await page.screenshot({path:testInfo.outputPath('bills-settings.png'),fullPage:true});
await page.locator('.console-view').evaluate(node => { node.scrollTop=0; });
await page.screenshot({path:testInfo.outputPath('bills-desktop.png'),fullPage:false});
failRun=true;await page.getByRole('button',{name:'Run bill entry',exact:true}).click();await page.getByText('Synthetic run failed',{exact:true}).waitFor();assert.equal(runs.at(-1).config.input_format,'image');assert.equal(runs.at(-1).config.review_mode,'only_exceptions');assert.equal(runs.at(-1).config.company_mode,'locked');assert.equal(runs.at(-1).config.locked_company_guid,'company');assert.equal(runs.at(-1).catalog_id,null);assert.equal(runs.at(-1).file_ids.includes('new'),false);
await page.getByLabel('Review mode',{exact:true}).selectOption('all_outputs');
failRun=false;await page.getByRole('button',{name:'Run bill entry',exact:true}).click();await page.waitForURL('**/tasks/run-task');assert.equal(runs.at(-1).config.review_mode,'all_outputs');
await open();assert.equal(await page.getByLabel('Bill inputs',{exact:true}).inputValue(),'pdf');
// Responsive layout and dark theme tokens.
await page.setViewportSize({width:390,height:844});await page.screenshot({path:testInfo.outputPath('bills-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
await page.evaluate(()=>document.documentElement.dataset.theme='slate-dark');await page.screenshot({path:testInfo.outputPath('bills-dark.png'),fullPage:true});
await page.setViewportSize({width:1440,height:1000});
await page.goto('http://127.0.0.1:3000/mock-tenant/connections');await page.getByRole('heading',{name:'QA PC',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Check Tally connection',exact:true}).count(),0);assert.equal(jobs.length,0);assert.equal(await page.getByRole('heading',{name:'Other owner PC',exact:true}).count(),0);
await page.getByRole('article').filter({has:page.getByRole('heading',{name:'QA PC',exact:true})}).getByRole('button',{name:'Check connections',exact:true}).click();assert.equal(jobs.length,0);await page.getByRole('region',{name:'Connections on QA PC',exact:true}).waitFor();await page.screenshot({path:testInfo.outputPath('connections-desktop.png'),fullPage:true});
await page.getByRole('button',{name:'Check Tally connection',exact:true}).click();await page.waitForURL('**/tasks/probe-task');assert.equal(jobs.at(-1).device_id,'pc');assert.equal(jobs.at(-1).operation,'tally.probe');assert.deepEqual(jobs.at(-1).input,{});assert.ok(jobs.at(-1).request_key);
await page.goto('http://127.0.0.1:3000/mock-tenant/connections');await page.getByRole('heading',{name:'Offline PC',exact:true}).waitFor();const offline=page.getByRole('article').filter({has:page.getByRole('heading',{name:'Offline PC',exact:true})});await offline.getByRole('button',{name:'Check connections',exact:true}).click();await page.getByText('This PC is offline. The check waits until it reconnects.').waitFor();const expired=page.getByRole('article').filter({has:page.getByRole('heading',{name:'Expired PC',exact:true})});assert.equal(await expired.getByRole('button',{name:'Check connections',exact:true}).isDisabled(),true);
await page.setViewportSize({width:390,height:844});await page.screenshot({path:testInfo.outputPath('connections-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
// Member run overrides must never gain saved-default/status editing privileges.
member=true;await open();assert.equal(await page.getByRole('button',{name:'Save as defaults',exact:true}).count(),0);assert.equal(await page.getByLabel('Status',{exact:true}).isDisabled(),true);await page.getByLabel('Bill inputs',{exact:true}).selectOption('mixed');assert.equal(defaults.input_format,'pdf');
// Explicit empty and stale choices persist; invalid values recover.
for(const [raw,expected] of [['[]',0],['["upload:gone.pdf"]',0],['{}',5],['null',5],['[1]',5]]){
 await page.evaluate(raw=>localStorage.setItem('mock-tenant:bill-entry:selections:v1',raw),raw);await page.reload();await page.getByRole('button',{name:'Run bill entry',exact:true}).waitFor();await page.waitForFunction(expected=>document.querySelector('[aria-label="Bill files"]')?.textContent?.includes(`${expected} of 5 selected`),expected);assert.equal(await checks().evaluateAll(inputs=>inputs.filter(i=>i.checked).length),expected);
}
// Native reconnect cancellation performs no upload; folder refresh rotates IDs without losing choices.
await page.evaluate(() => { window.minkopsDesktop = {version:1,status:async()=>({version:'synthetic',name:'QA PC',device:null}),pickFolder:async()=>null}; });
await page.getByRole('button',{name:'Reconnect folder',exact:true}).click();await page.getByText('Folder selection cancelled.',{exact:true}).waitFor();
await page.getByRole('button',{name:'Clear selection',exact:true}).click();await checks().nth(2).check();
await page.getByRole('button',{name:'Refresh folder',exact:true}).click();await page.getByText('fresh.pdf',{exact:true}).waitFor();assert.equal(await checks().nth(2).isChecked(),true);assert.equal(await checks().nth(4).isChecked(),false);
await page.reload();await page.getByRole('button',{name:'Run bill entry',exact:true}).waitFor();assert.equal(await checks().nth(2).isChecked(),true);
// Source-load failure preserves choices and offers an explicit retry.
await page.evaluate(()=>localStorage.setItem('mock-tenant:bill-entry:selections:v1','["upload:invoice-a.PDF"]'));failLoad=true;await page.reload();await page.getByText('Synthetic source load failed',{exact:true}).waitFor();assert.equal(await page.evaluate(()=>localStorage.getItem('mock-tenant:bill-entry:selections:v1')),'["upload:invoice-a.PDF"]');failLoad=false;
await page.getByRole('button',{name:'Retry loading files',exact:true}).click();await page.getByText('invoice-a.PDF',{exact:true}).waitFor();assert.equal(await checks().nth(0).isChecked(),true);
// Empty inventories provide an actionable empty state and disable launching.
sources=[];await page.reload();await page.getByText('No supported bills yet. Upload files or connect a folder to begin.',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Run bill entry',exact:true}).isDisabled(),true);
// Stale locked identities and unconfirmed catalogs cannot enable a Tally run.
sources=[{id:'upload',label:'Synthetic uploads',writable:false,files:[{id:'a',path:'invoice-a.PDF',sha256:'a'}]}];
await page.evaluate(()=>localStorage.removeItem('mock-tenant:bill-entry:selections:v1'));
defaults={...defaults,company_mode:'locked',locked_company_guid:'missing'};await open();assert.equal(await page.getByRole('button',{name:'Run bill entry',exact:true}).isDisabled(),true);
assert.equal(await page.getByRole('option',{name:'Excel',exact:true}).count(),0);
assert.equal(await page.getByRole('option',{name:'Both',exact:true}).count(),0);
defaults={...defaults,company_mode:'infer'};catalog.ready=false;await open();assert.equal(await page.getByRole('button',{name:'Run bill entry',exact:true}).isDisabled(),true);catalog.ready=true;
assert.equal(await page.locator('vite-error-overlay').count(),0);
// Browser preference storage may be blocked without blocking an authorized run.
sources=[{id:'upload',label:'Synthetic uploads',writable:false,files:[{id:'a',path:'invoice-a.PDF',sha256:'a'}]}];
await context.addInitScript(() => {
  Storage.prototype.getItem = () => { throw new Error('Synthetic storage denial'); };
  Storage.prototype.setItem = () => { throw new Error('Synthetic storage denial'); };
});
await open();await page.getByRole('button',{name:'Run bill entry',exact:true}).click();await page.waitForURL('**/tasks/run-task');
// Deliberate HTTP error responses above produce expected Chromium resource errors.
const unexpected=errors.filter(error=>!error.includes('the server responded with a status of 400')&&!error.includes('the server responded with a status of 503'));
assert.deepEqual(unexpected,[]);
console.log('PASS: mocked browser selection, persistence, upload, defaults/override, Tally approval, device context/ownership/expiry, desktop/mobile, page identity and console checks');
});
