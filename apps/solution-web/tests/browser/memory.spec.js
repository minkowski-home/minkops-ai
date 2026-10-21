/* global URL, document, window */
import {test, expect} from '@playwright/test';

const booking = {id:'e-1', kind:'booking', subject:'Sunrise Office Systems', status:'confirmed', uses:2, misses:0,
  company:'Test Company', value:{voucher_type:'Purchase', ledgers:['Input CGST 9%', 'Office Cabins']},
  evidence:[{kind:'outcome'}, {kind:'outcome'}], updated_at:'2026-10-21T10:00:00Z'};
const practice = {id:'e-2', kind:'practice', subject:'receipt_register', status:'confirmed', uses:0, misses:0,
  company:'Test Company', value:{recorded_in:'narration'}, evidence:[{kind:'answer'}], updated_at:'2026-10-21T10:00:00Z'};

async function memoryPage(context, {admin}) {
  const calls = [];
  let rules = [{id:'r-1', version:1, text:'Book both legs of a NEFT return.', status:'active', workflow:'statement-entry',
    company:null, company_id:null, updated_at:'2026-10-21T10:00:00Z'}];
  let entries = [booking, practice];
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    const base = '/api/tenants/mock-tenant/clients/rehearsal/memory';
    let body;
    if (path === '/api/auth/session') body = {id:'user', name:'QA', memberships:[{slug:'mock-tenant', role:admin ? 'admin' : 'member'}], csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant', name:'QA'}, can_edit:admin, employees:[], workflows:[], tasks:[]};
    else if (path.endsWith('/clients')) body = [{id:'c-1', slug:'rehearsal', name:'Rehearsal companies'}];
    else if (path.endsWith('/clients/rehearsal/companies')) body = [{id:'co-1', name:'Test Company'}];
    else if (path === base && method === 'GET') body = {can_edit:admin, entries, rules};
    else if (path.startsWith(base)) {
      calls.push([method, path.slice(base.length), request.postDataJSON()]);
      const id = path.split('/').at(-1);
      if (path.includes('/entries/')) {
        const status = request.postDataJSON().status;
        entries = status === 'retired' ? entries.filter(entry => entry.id !== id)
          : entries.map(entry => entry.id === id ? {...entry, status} : entry);
        body = {id, status};
      } else if (method === 'POST') {
        rules = [...rules, {id:'r-2', version:1, status:'active', company:null, ...request.postDataJSON(),
          workflow:request.postDataJSON().workflow_key}];
        body = rules.at(-1);
      } else if (method === 'PUT') {
        rules = rules.map(rule => rule.id === id ? {...rule, text:request.postDataJSON().text, version:rule.version + 1} : rule);
        body = rules.find(rule => rule.id === id);
      } else if (method === 'DELETE') { rules = rules.filter(rule => rule.id !== id); body = {id, status:'deleted'}; }
    } else throw Error(path);
    await route.fulfill({json:body});
  });
  return calls;
}

test('admins disable what was learnt and write, edit and delete rules', async ({page, context}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const calls = await memoryPage(context, {admin:true});
  await page.goto('http://127.0.0.1:3000/mock-tenant/memory');
  const learnt = page.locator('article').filter({hasText:'Sunrise Office Systems'});
  await expect(learnt).toContainText('Voucher type: Purchase · Ledgers: Input CGST 9%, Office Cabins');
  await expect(learnt).toContainText('Confirmed · learnt from 2 approved bills · used 2 times');
  await expect(page.locator('article').filter({hasText:'Receipt register'})).toContainText('answered by a person');
  for (const theme of ['minkops-light', 'minkops-dark', 'slate-light', 'slate-dark']) {
    await page.getByRole('combobox', {name:'Theme', exact:true}).selectOption(theme);
    await page.screenshot({path:testInfo.outputPath(`memory-${theme}.png`), fullPage:true});
  }
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await learnt.getByRole('button', {name:'Disable'}).click();
  await expect(learnt).toContainText('Disabled');
  await page.getByRole('textbox', {name:'Rule'}).fill('Site notes name the cost centre.');
  await page.getByRole('combobox', {name:'Workflow'}).selectOption('bill-entry');
  await page.getByRole('combobox', {name:'Company'}).selectOption('co-1');
  await page.getByRole('button', {name:'Add rule'}).click();
  await expect(page.getByRole('status')).toContainText('Rule added.');
  const neft = page.locator('article').filter({hasText:'NEFT return'});
  await neft.getByRole('button', {name:'Edit'}).click();
  await neft.getByRole('textbox', {name:'Rule'}).fill('NEFT returns: book both legs.');
  await neft.getByRole('button', {name:'Save'}).click();
  await expect(page.locator('article').filter({hasText:'NEFT returns: book both legs.'})).toContainText('version 2');
  await page.locator('article').filter({hasText:'NEFT returns: book both legs.'}).getByRole('button', {name:'Delete'}).click();
  await expect(page.getByRole('status')).toContainText('Rule deleted.');
  expect(calls).toEqual([
    ['PATCH', '/entries/e-1', {status:'disabled'}],
    ['POST', '/rules', {text:'Site notes name the cost centre.', workflow_key:'bill-entry', company_id:'co-1'}],
    ['PUT', '/rules/r-1', {text:'NEFT returns: book both legs.', workflow_key:'statement-entry', company_id:null}],
    ['DELETE', '/rules/r-1', null],
  ]);
  expect(errors).toEqual([]);
});

test('members read memory without the controls that change it', async ({page, context}) => {
  await memoryPage(context, {admin:false});
  await page.goto('http://127.0.0.1:3000/mock-tenant/memory');
  await expect(page.locator('article').filter({hasText:'Sunrise Office Systems'})).toBeVisible();
  await expect(page.getByRole('button', {name:/Disable|Delete|Edit|Add rule/})).toHaveCount(0);
});
