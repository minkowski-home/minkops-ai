/* global URL, document, window */
import { test, expect } from '@playwright/test';

const activePC = (id, name) => ({id,name,owner_id:'user',revoked_at:null,expires_at:'2099-01-01',last_seen_at:new Date().toISOString()});
const discovery = (device, company) => ({id:`catalog-${device}`,device_id:device,ready:true,config:{tally:{}},catalog:{excel_catalog_id:`excel-${device}`,sources:[{tool:'tally',snapshot:{companies:[{company,company_guid:`company-${device}`} ]}}]}});

test('web destination selection scopes catalogs, persists routing and never falls back between PCs', async ({ page, context }, testInfo) => {
  let devices=[activePC('a','PC A'),{...activePC('b','PC B'),last_seen_at:null},activePC('c','PC C'),{...activePC('expired','Expired PC'),expires_at:'2000-01-01'},{...activePC('foreign','Other account PC'),owner_id:'other'}];
  let failPCs=false, failCatalog=false, holdA=true;
  let releaseA;
  const delayedA=new Promise(resolve=>{releaseA=resolve;});
  const requested=[], completed=[], runs=[], errors=[];
  const catalogs={a:discovery('a','Company A'),b:discovery('b','Company B')};
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error'&&!message.text().includes('status of 503'))errors.push(message.text());});
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname;
    let body=null,status=200;
    if(path==='/api/auth/session') body={id:'user',name:'Synthetic User',email:'qa@example.test',memberships:[{slug:'mock-tenant',name:'Mock',role:'admin'}],csrf_token:'csrf'};
    else if(path.endsWith('/workspace')) body={tenant:{slug:'mock-tenant',name:'Synthetic multi-PC workspace'},can_edit:true,employees:[],tasks:[],workflows:[
      {id:'bill',key:'bill-entry',presentation:'accounts-bill',name:'Bill entry',status:'active',employee_ids:[],config_values:{output_mode:'tally_in_place',input_format:'mixed',review_mode:'all_outputs'},config_schema:{properties:{output_mode:{type:'string',title:'Output platform',enum:['tally_in_place','excel_in_place']}}}},
      {id:'future',key:'future-example',presentation:'proposal',name:'Future workflow',status:'active',employee_ids:[],config_values:{},config_schema:{properties:{}},run_schema:{properties:{}}},
    ]};
    else if(path.endsWith('/desktop/devices')){body=devices;if(failPCs){status=503;body={detail:'Synthetic PCs unavailable'};}}
    else if(path.endsWith('/accounts/sources'))body=[{id:'upload',label:'Synthetic bills',writable:false,files:[{id:'bill-file',path:'bill.pdf',sha256:'synthetic'}]}];
    else if(path.endsWith('/accounts/catalogs'))body=['a','b'].map(device=>({id:`excel-${device}`,confirmed_at:'2026-10-12',catalog:{sheets:[{role:'destination',file_id:`sheet-${device}`} ]}}));
    else if(path.endsWith('/discovery/latest')){
      const id=url.searchParams.get('device_id');requested.push(id);
      if(id==='a'&&holdA)await delayedA;
      body=id?catalogs[id]??null:catalogs.b;
      if(failCatalog){status=503;body={detail:'Synthetic discovery unavailable'};}
      completed.push(id);
    }
    else if(path.includes('/discovery/runs/catalog-'))body=Object.values(catalogs).find(catalog=>path.endsWith(catalog.id));
    else if(path.endsWith('/accounts/runs')&&request.method()==='POST'){
      runs.push(request.postDataJSON());expect(request.headers()['x-csrf-token']).toBe('csrf');body={task_id:'task'};
    }
    else if(path.endsWith('/run'))body=null;
    else if(path.includes('/tasks/'))body={id:'task',title:'Synthetic task',workflow_id:'bill',status:'running',progress:0,events:[]};
    else throw new Error(`Unmocked request ${path}`);
    await route.fulfill({status,json:body});
  });
  const route='http://127.0.0.1:3000/mock-tenant';
  const picker=page.getByLabel('Destination PC',{exact:true});
  const run=page.getByRole('button',{name:'Run bill entry',exact:true});
  await page.goto(`${route}/workflows/bill`);
  await expect(picker.getByRole('option',{name:'PC A · ready',exact:true})).toHaveCount(1);
  await expect(picker).toHaveValue('');await expect(run).toBeDisabled();expect(requested).toEqual([]);
  await expect(picker.getByRole('option',{name:'Other account PC',exact:false})).toHaveCount(0);
  expect(await picker.getByRole('option',{name:'Expired PC · reconnect required',exact:true}).evaluate(option=>option.disabled)).toBe(true);
  await picker.selectOption('a');await expect.poll(()=>requested.includes('a')).toBe(true);await expect(run).toBeDisabled();
  await picker.selectOption('b');await expect(run).toBeEnabled();await page.getByText('Destination and checks',{exact:true}).click();
  await page.getByLabel('Company selection',{exact:true}).selectOption('locked');await expect(page.getByLabel('Company for all bills',{exact:true})).toHaveValue('company-b');
  releaseA();holdA=false;await expect.poll(()=>completed.includes('a')).toBe(true);
  await expect(page.getByLabel('Company for all bills',{exact:true})).toHaveValue('company-b');
  await expect(page.getByText('This PC is offline. Local work waits for it to reconnect.')).toBeVisible();
  await page.locator('.console-view').evaluate(node=>{node.scrollTop=0;});await page.screenshot({path:testInfo.outputPath('destination-desktop.png')});
  await run.click();await page.waitForURL('**/tasks/task');expect(runs.at(-1).destination_device_id).toBe('b');expect(runs.at(-1).config.discovery_id).toBe('catalog-b');expect(runs.at(-1).config.locked_company_guid).toBe('company-b');
  await page.goto(`${route}/workflows/bill`);await expect(picker).toHaveValue('b');await expect(run).toBeEnabled();
  await picker.selectOption('a');await expect(run).toBeEnabled();await run.click();await page.waitForURL('**/tasks/task');expect(runs.at(-1).destination_device_id).toBe('a');expect(runs.at(-1).config.discovery_id).toBe('catalog-a');
  // PC B is globally newer, but Quick Run still uses the explicitly saved PC A.
  await page.goto(`${route}/dashboard`);await page.getByRole('article').filter({has:page.getByRole('heading',{name:'Bill entry',exact:true})}).getByRole('button',{name:'Run workflow',exact:true}).click();
  await page.waitForURL('**/tasks/task');expect(runs.at(-1).destination_device_id).toBe('a');expect(runs.at(-1).config.discovery_id).toBe('catalog-a');
  // A selection changed without launching cannot silently use the old Quick Run target.
  await page.goto(`${route}/workflows/bill`);await picker.selectOption('b');await page.goto(`${route}/dashboard`);
  const previous=runs.length;await page.getByRole('article').filter({has:page.getByRole('heading',{name:'Bill entry',exact:true})}).getByRole('button',{name:'Run workflow',exact:true}).click();await page.waitForURL('**/workflows/bill');expect(runs.length).toBe(previous);
  await picker.selectOption('c');await expect(run).toBeDisabled();await page.getByText('Destination and checks',{exact:true}).click();
  await expect(page.getByText('Run and confirm complete Tally Source Discovery on PC C first.',{exact:true})).toBeVisible();
  await picker.selectOption('a');await expect(run).toBeEnabled();await page.getByLabel('Output platform',{exact:true}).selectOption('excel_in_place');
  await expect(page.getByLabel('Confirmed sources',{exact:true})).toHaveValue('excel-a');expect(await page.getByLabel('Confirmed sources',{exact:true}).locator('option[value="excel-b"]').count()).toBe(0);
  await run.click();await page.waitForURL('**/tasks/task');expect(runs.at(-1).destination_device_id).toBe('a');expect(runs.at(-1).catalog_id).toBe('excel-a');
  // A persisted PC that disappears must remain an unavailable choice, even with one PC left.
  devices=[activePC('b','PC B')];await page.goto(`${route}/workflows/bill`);await expect(picker).toHaveValue('a');await expect(run).toBeDisabled();await expect(page.getByText('The selected PC is unavailable. Reconnect it or explicitly choose another PC.')).toBeVisible();
  await picker.selectOption('b');await expect(run).toBeEnabled();
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:testInfo.outputPath('destination-mobile.png'),fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  failCatalog=true;await page.reload();await expect(page.getByText('Synthetic discovery unavailable',{exact:true})).toBeVisible();await expect(run).toBeDisabled();failCatalog=false;
  failPCs=true;await page.reload();await expect(page.getByText('Synthetic PCs unavailable',{exact:true})).toBeVisible();await expect(run).toBeDisabled();failPCs=false;
  await page.getByRole('button',{name:'Retry loading PCs',exact:true}).click();await expect(run).toBeEnabled();
  // The installed proposal presentation inherits selection without a workflow-specific component.
  await page.goto(`${route}/workflows/future`);await expect(picker).toHaveValue('b');await page.locator('.accounts-sources > summary').first().click();await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Run workflow',exact:true}).click();await page.waitForURL('**/tasks/task');expect(runs.at(-1).destination_device_id).toBe('b');expect(runs.at(-1).config).toEqual({});
  await page.goto(`${route}/workflows/future`);await picker.selectOption('');await page.locator('.accounts-sources > summary').first().click();await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Run workflow',exact:true}).click();await page.waitForURL('**/tasks/task');expect(runs.at(-1).destination_device_id).toBe(null);
  expect(errors).toEqual([]);
});

test('an approved PC destination never falls back to another PC or browser folder', async ({page,context}) => {
  let bindings=[{source_id:'source',device_id:'b'}];
  let jobs=0;
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/desktop/sources'))await route.fulfill({json:bindings});
    else if(path.endsWith('/desktop/jobs')){jobs++;await route.fulfill({status:400,json:{detail:'Wrong destination job attempted'}});}
    else await route.fulfill({json:null});
  });
  await page.goto('http://127.0.0.1:3000/login');
  const attempt=()=>page.evaluate(async()=>{
    const {applyLocalPlan}=await import('/src/starter/accounts/localFiles.ts');
    try {await applyLocalPlan('mock-tenant','run',{id:'write',source_id:'source',path:'synthetic.xlsx'},'csrf','a');return 'unexpected success';}
    catch(error){return error.message;}
  });
  expect(await attempt()).toContain('selected destination PC');expect(jobs).toBe(0);
  bindings=[];expect(await attempt()).toContain('selected destination PC');expect(jobs).toBe(0);
});
