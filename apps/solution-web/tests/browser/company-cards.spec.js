/* global URL, document, window */
import {test, expect} from '@playwright/test';

const reason = (name, rest) => `${name} is open in Tally on NEW-PC. ${rest}`;
const found = (id, name, card, rest) => ({id, task_id:'sync', identifier:name, label:'New company found', status:'pending',
  workflow:'', employee:'', kind:'company', client:null, updated_at:'2026-10-22T10:00:00Z', reason:reason(name, rest),
  ...(card ? {card:{company_id:`co-${id}`, name, device:'NEW-PC', ...card}} : {})});

/** The attention page with three found companies, as an admin (with each card's details) or a member (without). */
async function attention(context, {admin}) {
  const calls = [];
  let items = [
    found('moved', 'Pradeep Infra', admin && {continues:{client:'pr-infra', client_name:'PR Infra', device:'OLD-PC'}},
      'These books were on OLD-PC, which is disconnected. Continue them here to keep what Minkops learnt for them, their rules and their history.'),
    found('fresh', 'Sunrise Traders', admin && {}, "Add it to a client's books?"),
    found('held', 'Third Company', admin && {held_on:'OTHER-PC'},
      "These books are already a client's on OTHER-PC, and a client's books are saved to one copy. To move them here, disconnect OTHER-PC first."),
  ];
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let body, status = 200;
    if (path === '/api/auth/session') body = {id:'user', name:'QA', memberships:[{slug:'mock-tenant', role:admin ? 'admin' : 'member'}], csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant', name:'QA'}, can_edit:admin, employees:[], workflows:[], tasks:[]};
    else if (path.endsWith('/attention')) body = items;
    else if (path.endsWith('/clients')) body = [{id:'c-1', slug:'pr-infra', name:'PR Infra', can_edit:admin},
      {id:'c-2', slug:'sunrise', name:'Sunrise Group', can_edit:admin}];
    else if (path.startsWith('/api/tenants/mock-tenant/companies/')) {
      const [, , , , , company, decision] = path.split('/');
      calls.push([company, decision, request.postDataJSON()]);
      if (company === 'co-held') { status = 409; body = {detail:'These books are already PR Infra\'s on OTHER-PC.'}; }
      else {
        items = items.filter(item => item.card.company_id !== company);
        body = {id:company === 'co-moved' ? 'co-original' : company, status:decision === 'decline' ? 'declined' : 'authorised'};
      }
    } else throw Error(path);
    await route.fulfill({status, json:body});
  });
  return calls;
}

test('an admin continues a client\'s books from the card, adds new books to a client, or keeps them out', async ({page, context}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const calls = await attention(context, {admin:true});
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  const moved = page.locator('article').filter({hasText:'Pradeep Infra'});
  await expect(moved).toContainText('These books were on OLD-PC, which is disconnected.');
  await expect(moved.getByRole('button', {name:'Mark as Done'})).toHaveCount(0);
  // Adding them to another client is offered apart; the client they continue is the one-click button alone.
  await expect(moved.getByRole('combobox', {name:'Client for Pradeep Infra'}).locator('option')).toHaveText(['Sunrise Group']);
  await expect(moved.getByRole('button')).toHaveText(["Continue PR Infra's books here", 'Add to Sunrise Group',
    "Not a client's books"]);
  // Books another connected PC holds are not added here; they can only be kept out.
  const held = page.locator('article').filter({hasText:'Third Company'});
  await expect(held.getByRole('combobox')).toHaveCount(0);
  await expect(held.getByRole('button')).toHaveText(["Not a client's books"]);
  for (const theme of ['minkops-light', 'minkops-dark', 'slate-light', 'slate-dark']) {
    await page.getByRole('combobox', {name:'Theme', exact:true}).selectOption(theme);
    await page.screenshot({path:testInfo.outputPath(`company-cards-${theme}.png`), fullPage:true});
  }
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('company-cards-mobile.png'), fullPage:true});
  await page.setViewportSize({width:1440, height:1000});
  // One click continues the client's company, the client named only to admins.
  await moved.getByRole('button', {name:"Continue PR Infra's books here"}).click();
  await expect(page.getByRole('status')).toHaveText("Continued PR Infra's books on NEW-PC");
  await expect(moved).toHaveCount(0);
  // New books go to the client chosen for them.
  const fresh = page.locator('article').filter({hasText:'Sunrise Traders'});
  await fresh.getByRole('combobox', {name:'Client for Sunrise Traders'}).selectOption('sunrise');
  await fresh.getByRole('button', {name:'Add to Sunrise Group'}).click();
  await expect(page.getByRole('status')).toHaveText('Added to Sunrise Group');
  // A refusal says why, and nothing changes.
  await held.getByRole('button', {name:"Not a client's books"}).click();
  await expect(page.getByRole('status')).toContainText("already PR Infra's on OTHER-PC");
  await expect(held).toHaveCount(1);
  expect(calls).toEqual([['co-moved', 'authorise', {client:'pr-infra'}], ['co-fresh', 'authorise', {client:'sunrise'}],
    ['co-held', 'decline', null]]);
  expect(errors).toEqual([]);
});

test('a member reads the card but leaves the decision to an admin', async ({page, context}) => {
  const calls = await attention(context, {admin:false});
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  const moved = page.locator('article').filter({hasText:'Pradeep Infra'});
  await expect(moved).toContainText('These books were on OLD-PC');
  await expect(moved).toContainText('A workspace admin decides whose books these are.');
  await expect(page.locator('article').getByRole('button')).toHaveCount(0);
  await expect(page.getByText('PR Infra', {exact:false})).toHaveCount(0);
  expect(calls).toEqual([]);
});
