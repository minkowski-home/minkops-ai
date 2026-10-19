/* global URL */
import {test,expect} from '@playwright/test';

for(const withMapping of [false,true])test(`AI statement launch and quick run preserve sources ${withMapping?'with':'without'} optional mapping`,async({page,context})=>{
 let fileId='file',mappingAvailable=true; const errors=[],runs=[];page.on('pageerror',e=>errors.push(e.message));
 const workflow={id:'statement',key:'statement-entry',presentation:'accounts-statement',name:'Statement entry',status:'active',employee_ids:[],
  config_values:{review_mode:'all_outputs',date_format:'dmy',opening_balance:''},config_schema:{properties:{}}};
 await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
 await context.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;let body;
  if(path==='/api/auth/session')body={id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
  else if(path.endsWith('/workspace'))body={tenant:{slug:'mock-tenant',name:'QA'},can_edit:true,employees:[],workflows:[workflow],tasks:[]};
  else if(path.endsWith('/desktop/devices'))body=[{id:'pc',name:'QA PC',owner_id:'user',expires_at:'2099-01-01',revoked_at:null,last_seen_at:new Date().toISOString(),companion_version:'0.8.0'}];
  else if(path.endsWith('/accounts/sources'))body=[{id:'source',label:'Bank files',writable:false,files:[{id:fileId,path:'statement.csv'},...(mappingAvailable?[{id:fileId+'-mapping',path:'branch-mapping.xlsx'}]:[])]}];
  else if(path.endsWith('/discovery/latest'))body={id:'discovery',device_id:'pc',ready:true,catalog:{sources:[{tool:'tally',snapshot:{companies:[{company:'Test Company',company_guid:'company',masters:{status:'ready',count:200},statement_options:{banks:[{name:'Discovered Bank',guid:'bank'}],voucher_types:[]}}]}}]}};
  else if(path.endsWith('/accounts/runs')){runs.push(route.request().postDataJSON());body={task_id:'task'};}
  else if(path.endsWith('/discovery/tasks/task')||path.endsWith('/accounts/tasks/task/run'))body=null;
  else if(path.includes('/tasks/task'))body={id:'task',title:'Statement entry',workflow_id:'statement',status:'running',progress:0,events:[]};
  else throw Error(path);
  await route.fulfill({json:body});
 });
 await page.goto('http://127.0.0.1:3000/mock-tenant/workflows/statement');
 await page.getByLabel('statement.csv',{exact:true}).check();
 await expect(page.getByText('Bank destinations',{exact:true})).toHaveCount(0);
 if(withMapping){
  await page.getByLabel('branch-mapping.xlsx',{exact:true}).check();
  await page.getByLabel('Branch mapping (optional)',{exact:true}).selectOption('file-mapping');
  await expect(page.getByLabel('branch-mapping.xlsx',{exact:true})).not.toBeChecked();
  await expect(page.getByLabel('branch-mapping.xlsx',{exact:true})).toBeDisabled();
 }
 await page.getByRole('button',{name:'Interpret statements',exact:true}).click();
 await page.waitForURL('**/tasks/task');
 expect(runs[0].config.branch_mapping_file_id).toBe(withMapping?'file-mapping':null);
 expect(runs[0].config.bank_ledgers).toBeUndefined();
 expect(runs[0].config.other_side_ledger).toBeUndefined();
 expect(runs[0].config.discovery_id).toBe('discovery');
 expect(runs[0].destination_device_id).toBe('pc');
 expect(runs[0].file_ids).toEqual(['file']);
 // Preferences use source/path identities even when a refresh replaces IDs.
 fileId='refreshed-file';
 await page.goto('http://127.0.0.1:3000/mock-tenant/workflows/statement');
 await expect(page.getByLabel('statement.csv',{exact:true})).toBeChecked();
 await expect(page.getByLabel('Branch mapping (optional)',{exact:true})).toHaveValue(withMapping?'refreshed-file-mapping':'');
 await page.goto('http://127.0.0.1:3000/mock-tenant/dashboard');
 await page.getByRole('button',{name:'Run workflow',exact:true}).click();
 await page.waitForURL('**/tasks/task');
 expect(runs).toHaveLength(2);
 expect(runs[1].file_ids).toEqual(['refreshed-file']);
 expect(runs[1].config.branch_mapping_file_id).toBe(withMapping?'refreshed-file-mapping':null);
 if(withMapping){
  mappingAvailable=false;
  await page.goto('http://127.0.0.1:3000/mock-tenant/workflows/statement');
  await expect(page.getByLabel('Branch mapping (optional)',{exact:true})).toHaveValue('missing');
  await expect(page.getByRole('button',{name:'Interpret statements',exact:true})).toBeDisabled();
  await page.getByLabel('Branch mapping (optional)',{exact:true}).selectOption('');
  await expect(page.getByRole('button',{name:'Interpret statements',exact:true})).toBeEnabled();
 }
 expect(errors).toEqual([]);
});
