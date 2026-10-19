/* global URL */
import {test,expect} from '@playwright/test';

test('statement launch uses compact discovery options and pins explicit bank routing',async({page,context})=>{
 const errors=[],runs=[];page.on('pageerror',e=>errors.push(e.message));
 const workflow={id:'statement',key:'statement-entry',presentation:'accounts-statement',name:'Statement entry',status:'active',employee_ids:[],
  config_values:{review_mode:'all_outputs',other_side_ledger:'Expense',counter_mode:'single',date_format:'dmy',opening_balance:''},config_schema:{properties:{}}};
 await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
 await context.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;let body;
  if(path==='/api/auth/session')body={id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
  else if(path.endsWith('/workspace'))body={tenant:{slug:'mock-tenant',name:'QA'},can_edit:true,employees:[],workflows:[workflow],tasks:[]};
  else if(path.endsWith('/desktop/devices'))body=[{id:'pc',name:'QA PC',owner_id:'user',expires_at:'2099-01-01',revoked_at:null,last_seen_at:new Date().toISOString(),companion_version:'0.8.0'}];
  else if(path.endsWith('/accounts/sources'))body=[{id:'source',label:'Bank files',writable:false,files:[{id:'file',path:'statement.csv'}]}];
  else if(path.endsWith('/discovery/latest'))body={id:'discovery',device_id:'pc',ready:true,catalog:{sources:[{tool:'tally',snapshot:{companies:[{company:'Test Company',company_guid:'company',masters:{status:'ready',count:200},statement_options:{banks:[{name:'Discovered Bank',guid:'bank'}],voucher_types:[]}}]}}]}};
  else if(path.endsWith('/accounts/runs')){runs.push(route.request().postDataJSON());body={task_id:'task'};}
  else if(path.endsWith('/discovery/tasks/task')||path.endsWith('/accounts/tasks/task/run'))body=null;
  else if(path.includes('/tasks/task'))body={id:'task',title:'Statement entry',workflow_id:'statement',status:'running',progress:0,events:[]};
  else throw Error(path);
  await route.fulfill({json:body});
 });
 await page.goto('http://127.0.0.1:3000/mock-tenant/workflows/statement');
 await page.getByLabel('statement.csv',{exact:true}).check();
 await page.getByLabel('Bank ledger for Test Company',{exact:true}).selectOption('Discovered Bank');
 await page.getByRole('button',{name:'Check statements',exact:true}).click();
 await page.waitForURL('**/tasks/task');
 expect(runs[0].config.bank_ledgers).toEqual({company:'Discovered Bank'});
 expect(runs[0].config.discovery_id).toBe('discovery');
 expect(runs[0].destination_device_id).toBe('pc');
 expect(runs[0].file_ids).toEqual(['file']);expect(errors).toEqual([]);
});
