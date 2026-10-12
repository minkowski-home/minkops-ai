/* global URL, document, window */
import { test, expect } from '@playwright/test';

test('generic workflow has one configuration owner and keeps run-only fields out of defaults', async ({page, context}, testInfo) => {
  const patches=[], runs=[];
  const workflow={id:'proposal',key:'example',name:'Example workflow',status:'active',presentation:'proposal',employee_ids:[],
    config_values:{review_mode:'all_outputs'},config_schema:{properties:{review_mode:{type:'string',title:'Default review mode',enum:['all_outputs','only_exceptions']}}},
    run_defaults:{limit:3},run_schema:{properties:{review_mode:{type:'string',enum:['all_outputs','only_exceptions']},limit:{type:'integer',title:'Files per run'}}}};
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;let body=null;
    if(path==='/api/auth/session')body={id:'user',name:'QA',email:'qa@example.test',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
    else if(path.endsWith('/workspace'))body={tenant:{slug:'mock-tenant',name:'Synthetic QA'},can_edit:true,employees:[],workflows:[workflow],tasks:[]};
    else if(path.endsWith('/accounts/sources'))body=[{id:'source',label:'Files',files:[{id:'file',path:'sample.pdf'}]}];
    else if(path.endsWith('/desktop/devices'))body=[];
    else if(path.endsWith('/workflows/proposal')&&req.method()==='PATCH'){patches.push(req.postDataJSON());workflow.config_values=req.postDataJSON().config_values;body={};}
    else if(path.endsWith('/accounts/runs')&&req.method()==='POST'){runs.push(req.postDataJSON());body={task_id:'task'};}
    else if(path.endsWith('/tasks/task'))body={id:'task',workflow_id:'proposal',title:'Example workflow',status:'running',created_at:new Date(Date.now()-89000).toISOString(),updated_at:new Date().toISOString(),events:[]};
    else if(path.endsWith('/accounts/tasks/task/run'))body={id:'run',state:'executing',result:null};
    else throw new Error(`Unhandled ${path}`);
    await route.fulfill({json:body});
  });
  const url='http://127.0.0.1:3000/mock-tenant/workflows/proposal';
  await page.goto(url);
  await expect(page.getByLabel('Review mode',{exact:true})).toHaveCount(1);
  await page.locator('.accounts-sources summary').click();
  await page.getByRole('checkbox',{name:'sample.pdf'}).check();
  await page.getByLabel('Files per run').fill('7');
  await page.getByLabel('Review mode',{exact:true}).selectOption('only_exceptions');
  await page.getByRole('button',{name:'Save as defaults'}).click();
  await expect(page.getByText('Defaults saved. This run keeps your selected options.')).toBeVisible();
  expect(patches.at(-1)).toEqual({config_values:{review_mode:'only_exceptions'}});
  await expect(page.getByLabel('Files per run')).toHaveValue('7');
  await page.getByRole('button',{name:'Reset to defaults'}).click();
  await expect(page.getByLabel('Files per run')).toHaveValue('3');
  await page.screenshot({path:testInfo.outputPath('generic-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:testInfo.outputPath('generic-mobile.png'),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.getByRole('button',{name:'Run workflow',exact:true}).click();
  await expect(page).toHaveURL(/tasks\/task$/);
  expect(runs.at(-1).config).toEqual({review_mode:'only_exceptions',limit:3});
  await expect(page.getByText(/Time since started: 1m/)).toBeVisible();
});
