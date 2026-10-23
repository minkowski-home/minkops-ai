/* global URL */
import { test, expect } from '@playwright/test';

const tenant = '/api/tenants/mock-tenant';
const workflow = {id:'statements',key:'statement-entry',name:'Statement entry',presentation:'desk-review',status:'active',employee_ids:[],config_schema:{properties:{}},config_values:{}};
const task = {id:'statement',workflow_id:'statements',title:'Statement entry: icici.csv',status:'running',stage:'executing',progress:5,summary:'0 of 2 parts read.',created_at:'2026-10-21T07:30:00Z',updated_at:'2026-10-21T07:31:00Z'};
const item = {id:'dates',task_id:'statement',identifier:'icici.csv',label:'Choose date order',reason:'Confirm how to read this statement.',status:'pending',workflow:'Statement entry',employee:'Accounts',kind:'layout',updated_at:'2026-10-21T07:31:00Z',
  question:{prompt:'Dates such as 01/02/2026 could be day-first or month-first.',
    options:[{action:'dmy',label:'Day first'},{action:'mdy',label:'Month first'}],samples:[]}};

async function fixture(context, overrides) {
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (await overrides?.(route, path)) return;
    let body;
    if (path === '/api/auth/session') body = {id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant',name:'QA'},attention_count:1,can_edit:true,employees:[],workflows:[workflow],tasks:[task]};
    else if (path === tenant + '/tasks/statement') body = {...task,events:[{event_type:'executing',summary:'0 of 2 parts read.'}]};
    else if (path.endsWith('/attention')) body = [item];
    else throw Error(`Unexpected request ${path}`);
    await route.fulfill({json:body});
  });
}

test('returning to Attention shows the items already read while they revalidate', async ({page, context}) => {
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
  await expect(page.getByRole('link',{name:'icici.csv',exact:true})).toBeVisible();
  hold = true;
  await page.getByRole('link',{name:'icici.csv',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'0 of 2 parts read.'})).toBeVisible();
  await page.getByRole('link',{name:'Attention items',exact:true}).click();
  // The revalidation is deliberately blocked: cached content must already render.
  await expect(page.getByRole('link',{name:'icici.csv',exact:true})).toBeVisible();
  await expect(page.getByText('Loading attention items…',{exact:true})).toHaveCount(0);
  release();
  expect(errors).toEqual([]);
});

test('an answer stays confirmed when the list fails to revalidate, and survives navigation', async ({page, context}) => {
  let release, committed = false, listReads = 0;
  const decision = new Promise(resolve => { release = resolve; });
  await fixture(context, async (route, path) => {
    if (path.endsWith('/decision') && route.request().method() === 'POST') {
      await decision; committed = true;
      await route.fulfill({json:{status:'active'}}); return true;
    }
    if (path.endsWith('/attention') && ++listReads > 1 && committed) {
      await route.fulfill({status:503,json:{detail:'Temporary list failure'}}); return true;
    }
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  await page.getByRole('button',{name:'Day first',exact:true}).click();
  await expect(page.getByRole('button',{name:'Confirming…',exact:true})).toBeDisabled();
  release();
  await expect(page.getByText('Confirmed; waiting work continues',{exact:true})).toBeVisible();
  await expect(page.getByText('Could not refresh attention items.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Day first',exact:true})).toHaveCount(0);
  await page.getByRole('link',{name:'Dashboard',exact:true}).click();
  await page.getByRole('link',{name:'Attention items',exact:true}).click();
  await expect(page.getByText('Confirmed; waiting work continues',{exact:true})).toBeVisible();
});

test('a lost answer response is reconciled from the member\'s receipt', async ({page, context}) => {
  let committed = false, receiptReads = 0;
  await fixture(context, async (route, path) => {
    if (path.endsWith('/decision') && route.request().method() === 'POST') {
      committed = true; await route.fulfill({status:504,json:{detail:'Response timed out'}}); return true;
    }
    if (path.endsWith('/decision')) {
      receiptReads++;
      await route.fulfill({json:{item_id:'dates',actor_id:'user',action:'dmy',status:'active',applied_at:'2026-10-21T07:32:00Z'}});
      return true;
    }
    if (path.endsWith('/attention') && committed) { await route.fulfill({json:[]}); return true; }
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  await page.getByRole('button',{name:'Day first',exact:true}).click();
  await expect(page.getByText('Confirmed; waiting work continues',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Day first',exact:true})).toHaveCount(0);
  expect(receiptReads).toBe(1);
});
