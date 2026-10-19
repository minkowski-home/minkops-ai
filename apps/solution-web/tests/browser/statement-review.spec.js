/* global URL, document, window */
import {test,expect} from '@playwright/test';

test('statement preview shows branch totals, exceptions first, immutable actions and CSV',async({page,context},testInfo)=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const row={source_file:'statement.csv',sheet:'',row:3,branch:'Test Company',date:'2026-10-01',reference:'PAY-1',amount_cents:-12731,balance_cents:87269,company:'Test Company',status:'ready'};
 let state='review';const decisions=[];
 const run=()=>({id:'run',actor_id:'user',task_id:'task',workflow_key:'statement-entry',state,config:{},writes:[],tally_writes:[],
  result:{records:[row,{...row,row:4,status:'held',code:'statement_balance',reason:'The running balance cannot be verified.'}],findings:[]}});
 await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
 await context.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;let body;
  if(path==='/api/auth/session')body={id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
  else if(path.endsWith('/workspace'))body={tenant:{slug:'mock-tenant',name:'QA'},can_edit:true,employees:[],workflows:[],tasks:[]};
  else if(path.endsWith('/discovery/tasks/task'))body=null;
  else if(path.endsWith('/accounts/tasks/task/run'))body=run();
  else if(path.endsWith('/approve')){decisions.push(route.request().postDataJSON());state='writing';body=run();}
  else if(path.endsWith('/statement-exceptions.csv')){await route.fulfill({body:'\ufeffSource file,Reason\r\nstatement.csv,Balance mismatch\r\n',contentType:'text/csv',headers:{'Content-Disposition':'attachment; filename="statement-exceptions-run.csv"'}});return;}
  else if(path.includes('/tasks/task'))body={id:'task',title:'Statement entry',status:'attention',progress:0,events:[]};
  else throw Error(path);
  await route.fulfill({json:body});
 });
 await page.goto('http://127.0.0.1:3000/mock-tenant/tasks/task');
 await expect(page.getByRole('heading',{name:'Statement preview'})).toBeVisible();
 await expect(page.locator('.accounts-bill').first()).toContainText('The running balance cannot be verified.');
 await expect(page.getByRole('cell',{name:'254.62',exact:true})).toBeVisible();
 const waiting=page.waitForEvent('download');await page.getByRole('button',{name:'Export CSV'}).click();
 expect((await waiting).suggestedFilename()).toBe('statement-exceptions-run.csv');
 await page.screenshot({path:testInfo.outputPath('statement-review-desktop.png')});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:testInfo.outputPath('statement-review-mobile.png')});
 await page.getByRole('button',{name:'Write ready rows'}).click();
 expect(decisions).toEqual([{result:{action:'write_ready'}}]);
 await expect(page.getByRole('button',{name:'Export CSV'})).toBeDisabled();
 expect(errors).toEqual([]);
});
