/* global URL */
import { test, expect } from '@playwright/test';

const tenant = '/api/tenants/mock-tenant';
const workflow = {id:'bill',key:'bill-entry',name:'Bill entry',presentation:'accounts-bill',status:'active',employee_ids:[],config_schema:{properties:{}},config_values:{}};
const task = {id:'bills',workflow_id:'bill',title:'Bill entry',status:'running',stage:'executing',progress:0,summary:'Reading bills',created_at:'2026-10-21T07:30:00Z',updated_at:'2026-10-21T07:31:00Z'};
const item = {id:'profile',task_id:'bills',identifier:'Pradeepraj Infra',label:'Confirm posting pattern',reason:'Confirm this company’s practice once.',status:'pending',workflow:'Bill entry',employee:'Accounts',updated_at:'2026-10-21T07:31:00Z',profile:{company:'Pradeepraj Infra',waiting:3,summary:['Invoice number in Reference']}};
const bill = {source_file_id:'office',status:'ready',operation:'append',data:{invoice_number:'UAT-OFFICE',total:188800},findings:[],evidence:[],allowed_actions:[]};
const run = {id:'run',actor_id:'user',task_id:'bills',workflow_key:'bill-entry',state:'executing',config:{file_provenance:[{id:'office',path:'B01-office.pdf'}]},writes:[],tally_writes:[],result:{records:[bill],findings:[]},
  blockers:[{kind:'profile',attention_item_id:'profile',company:'Pradeepraj Infra',label:'Confirm posting pattern',waiting:3}],
  execution:{stage:'awaiting_input',ready:1,total:3,active:0,queued:2,last_activity_at:'2026-10-21T07:31:00Z'}};

async function fixture(context, overrides) {
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (await overrides?.(route, path)) return;
    let body;
    if (path === '/api/auth/session') body = {id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant',name:'QA'},attention_count:1,can_edit:true,employees:[],workflows:[workflow],tasks:[task]};
    else if (path === tenant + '/tasks/bills') body = {...task,events:[{event_type:'executing'}]};
    else if (path.endsWith('/accounts/tasks/bills/run')) body = run;
    else if (path.endsWith('/attention')) body = [item];
    else throw Error(`Unexpected request ${path}`);
    await route.fulfill({json:body});
  });
}

test('return navigation retains results, avoids discovery probes and explains the exact blocker', async ({page, context}) => {
  const requests = [], errors = [];
  page.on('request', request => requests.push(new URL(request.url()).pathname));
  page.on('pageerror', error => errors.push(error.message));
  let release, hold = false;
  const delayed = new Promise(resolve => { release = resolve; });
  await fixture(context, async (route, path) => {
    if (path.endsWith('/attention') && hold) {
      await delayed; await route.fulfill({json:[item]}); return true;
    }
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  await expect(page.getByRole('link',{name:'Pradeepraj Infra',exact:true})).toBeVisible();
  const workspaceReads = requests.filter(path => path.endsWith('/workspace')).length;
  hold = true;
  await page.getByRole('link',{name:'Pradeepraj Infra',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Waiting for your confirmation'})).toBeVisible();
  await expect(page.locator('.accounts-bill > p').filter({hasText:'UAT-OFFICE'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Write bill',exact:true})).toHaveCount(0);
  const confirmation = page.getByRole('link',{name:'Open confirmation',exact:true});
  await expect(confirmation).toHaveAttribute('href','/mock-tenant/attention#attention-profile');
  await confirmation.click();
  // The revalidation is deliberately blocked: cached content must already render.
  await expect(page.getByRole('link',{name:'Pradeepraj Infra',exact:true})).toBeVisible();
  await expect(page.getByText('Loading attention items…',{exact:true})).toHaveCount(0);
  expect(requests.filter(path => path.includes('/discovery/tasks/'))).toEqual([]);
  expect(requests.filter(path => path.endsWith('/workspace'))).toHaveLength(workspaceReads);
  release();
  expect(errors).toEqual([]);
});

test('confirmation feedback stays successful when list revalidation fails and survives navigation', async ({page, context}) => {
  let release, committed = false, listReads = 0;
  const decision = new Promise(resolve => { release = resolve; });
  await fixture(context, async (route, path) => {
    if (path.endsWith('/profile')) {
      await decision; committed = true;
      await route.fulfill({json:{status:'active'}}); return true;
    }
    if (path.endsWith('/attention') && ++listReads > 1 && committed) {
      await route.fulfill({status:503,json:{detail:'Temporary list failure'}}); return true;
    }
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  await page.getByRole('button',{name:'Confirm',exact:true}).click();
  await expect(page.getByRole('button',{name:'Confirming…',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Refresh pending items',exact:true})).toBeVisible();
  release();
  await expect(page.getByText('Confirmed; waiting work continues',{exact:true})).toBeVisible();
  await expect(page.getByText('Could not refresh attention items.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Confirm',exact:true})).toHaveCount(0);
  await page.getByRole('link',{name:'Dashboard',exact:true}).click();
  await page.getByRole('link',{name:'Attention items',exact:true}).click();
  await expect(page.getByText('Confirmed; waiting work continues',{exact:true})).toBeVisible();
});

test('a lost decision response is reconciled from its actor receipt', async ({page, context}) => {
  let committed = false, receiptReads = 0;
  await fixture(context, async (route, path) => {
    if (path.endsWith('/profile')) {
      committed = true; await route.fulfill({status:504,json:{detail:'Response timed out'}}); return true;
    }
    if (path.endsWith('/decision')) {
      receiptReads++; await route.fulfill({json:{item_id:'profile',actor_id:'user',action:'confirm',status:'active',applied_at:'2026-10-21T07:32:00Z'}}); return true;
    }
    if (path.endsWith('/attention') && committed) { await route.fulfill({json:[]}); return true; }
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  await page.getByRole('button',{name:'Confirm',exact:true}).click();
  await expect(page.getByText('Confirmed; waiting work continues',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Confirm',exact:true})).toHaveCount(0);
  expect(receiptReads).toBe(1);
});
