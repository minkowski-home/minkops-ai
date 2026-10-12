/* global URL, document, window */
import { test, expect } from '@playwright/test';

test('AI-off persists for every source mode and goes directly to confirmable review', async ({ page, context }, testInfo) => {
  const errors = [], requests = [];
  let latest = null;
  const workflow = {id:'discovery',key:'source-discovery',presentation:'accounts-discovery',name:'Source discovery',status:'active',employee_ids:[],config_values:{destination_mode:'tally',max_files:45},config_schema:{properties:{destination_mode:{type:'string',enum:['tally','excel','both']},max_files:{type:'integer'}}}};
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let body = null;
    if (path === '/api/auth/session') body = {id:'user',name:'Synthetic User',email:'qa@example.test',memberships:[{slug:'mock-tenant',name:'Mock',role:'admin'}],csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant',name:'Synthetic workspace'},can_edit:true,employees:[],tasks:[],workflows:[workflow]};
    else if (path.endsWith('/workflows/discovery') && request.method() === 'PATCH') { expect(request.postDataJSON().status).toBeUndefined(); workflow.config_values = request.postDataJSON().config_values; body = {}; }
    else if (path.endsWith('/desktop/devices')) body = [{id:'pc',name:'QA PC',owner_id:'user',revoked_at:null,expires_at:'2099-01-01',last_seen_at:new Date().toISOString()}];
    else if (path.endsWith('/desktop/sources')) body = [{source_id:'folder',device_id:'pc'}];
    else if (path.endsWith('/accounts/sources')) body = [{id:'folder',label:'Books',files:[{id:'file',path:'register.xlsx'}]}];
    else if (path.endsWith('/discovery/latest')) body = latest;
    else if (path.endsWith('/discovery/runs') && request.method() === 'POST') {
      const payload = request.postDataJSON();
      requests.push(payload);
      expect(request.headers()['x-csrf-token']).toBe('csrf');
      latest = {id:'run',task_id:'task',device_id:'pc',config:payload.config,state:'review',ready:false,observations:[],mapping_run:null,
        catalog:{partial:false,review:{status:'required',reused_from:null},context_notes:[],excel_mappings:null,sources:[]}};
      body = latest;
    }
    else if (path.endsWith('/discovery/runs/run/confirm')) {
      latest = {...latest,state:'completed',ready:true,catalog:{...latest.catalog,review:{status:'confirmed',reused_from:null}}};
      body = latest;
    }
    else if (path.endsWith('/discovery/tasks/task')) body = latest;
    else if (path.endsWith('/accounts/tasks/task/run')) body = null;
    else if (path.endsWith('/tasks/task')) body = {id:'task',title:'Discover business sources',workflow_id:'discovery',status:latest?.ready?'completed':'attention',control_state:'active',progress:70,events:[]};
    else throw new Error(`Unmocked request ${path}`);
    await route.fulfill({json:body});
  });
  const root = 'http://127.0.0.1:3000/mock-tenant';
  for (const mode of ['Tally', 'Excel', 'Tally + Excel']) {
    await page.goto(`${root}/workflows/discovery`);
    const toggle = page.getByRole('checkbox', {name:/AI context analysis/});
    await expect(page.getByRole('radio',{name:'Tally',exact:true})).toBeChecked();
    if (!requests.length) await expect(toggle).toBeChecked();
    else { await expect(toggle).toBeChecked(); await page.getByRole('button',{name:'Use previous run settings'}).click(); await expect(toggle).not.toBeChecked(); }
    await page.getByRole('radio', {name:mode,exact:true}).check();
    await toggle.uncheck();
    if (mode !== 'Tally') await page.getByRole('checkbox', {name:/Books/}).check();
    await page.getByRole('button', {name:'Discover sources',exact:true}).click();
    await expect(page.getByRole('button', {name:'Confirm sources',exact:true})).toBeEnabled();
    await expect(page.getByText(/AI analysis is off/)).toBeVisible();
    expect(requests.at(-1).config.ai_context).toBe(false);
    if (mode === 'Excel') expect(requests.at(-1).config.tally).toBeNull();
    else expect(requests.at(-1).config.tally.port).toBe(9000);
    if (mode !== 'Tally') expect(requests.at(-1).config.excel_source_ids).toEqual(['folder']);
    await page.getByRole('button', {name:'Confirm sources',exact:true}).click();
    await expect(page.getByRole('heading', {name:'Your sources are ready',exact:true})).toBeVisible();
  }
  await page.goto(`${root}/workflows/discovery`);
  await page.getByRole('button',{name:'Use previous run settings'}).click();
  await page.getByRole('checkbox', {name:/AI context analysis/}).check();
  await page.screenshot({path:testInfo.outputPath('discovery-context-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:testInfo.outputPath('discovery-context-mobile.png'),fullPage:true});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', {name:'Discover sources',exact:true}).click();
  await expect.poll(() => requests.length).toBe(4);
  expect(requests.at(-1).config.ai_context).toBe(true);
  await page.goto(`${root}/workflows/discovery`);
  await page.getByRole('radio',{name:'Excel',exact:true}).check();
  await page.getByRole('button',{name:'Save as defaults'}).click();
  await expect(page.getByText('Defaults saved. This run keeps your selected options.')).toBeVisible();
  expect(workflow.config_values).toEqual({destination_mode:'excel',max_files:45});
  await page.reload();
  await expect(page.getByRole('radio',{name:'Excel',exact:true})).toBeChecked();
  await page.getByRole('button',{name:'Use previous run settings'}).click();
  await expect(page.getByRole('radio',{name:'Tally + Excel',exact:true})).toBeChecked();
  await page.getByRole('button',{name:'Reset to defaults'}).click();
  await expect(page.getByRole('radio',{name:'Excel',exact:true})).toBeChecked();
  expect(errors).toEqual([]);
});
