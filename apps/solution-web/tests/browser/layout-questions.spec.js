/* global URL, document, window */
import {test, expect} from '@playwright/test';

test('layout questions stay legible and submit only the offered answer; other items are marked done', async ({page, context}, testInfo) => {
  const errors = [], decisions = [];
  page.on('pageerror', error => errors.push(error.message));
  let items = [
    {id:'dates',task_id:'statement',identifier:'statement.csv',label:'Choose date order',status:'pending',workflow:'Statement entry',employee:'Accounts',kind:'layout',
      reason:'Confirm how to read this statement.',
      layout:{prompt:'Dates such as 03/04/26 could be day-first or month-first.',actions:['dmy','mdy'],samples:[{date:'2026-04-03',amount_cents:-11770,account:'Current account',narration:'Charges with GST'}]}},
    {id:'sample',task_id:'statement',identifier:'no-balance.csv',label:'Confirm statement layout',status:'pending',workflow:'Statement entry',employee:'Accounts',kind:'layout',
      reason:'Confirm how to read this statement.',
      layout:{prompt:'Confirm these sample rows; this file has no running balance.',actions:['confirm','nothing'],samples:[{date:'2026-10-02',amount_cents:1700,account:'',narration:'Interest'}]}},
    {id:'gap',task_id:'statement',identifier:'ICICI Current A/c',label:'Transactions missing',status:'pending',workflow:'Statement entry',employee:'Accounts',kind:'manual',
      reason:'ICICI Current A/c closed at 97000.00 on 2026-08-31 in an earlier statement, but this one opens at 107000.00 on 2026-09-01.'},
  ].map(item => ({...item, updated_at:'2026-10-20T10:00:00Z'}));
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body;
    if (path === '/api/auth/session') body = {id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant',name:'QA'},can_edit:true,employees:[],workflows:[],tasks:[]};
    else if (path.endsWith('/decision') && route.request().method() === 'POST') {
      decisions.push(route.request().postDataJSON());
      items = items.filter(item => !path.includes(`/${item.id}/`));
      body = {status:decisions.at(-1).action === 'nothing' ? 'superseded' : 'active'};
    } else if (path.endsWith('/done')) {
      items = items.filter(item => !path.includes(`/${item.id}/`));
      body = {status:'done'};
    } else if (path.endsWith('/attention')) body = items;
    else throw Error(path);
    await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/attention');
  const dates = page.locator('article').filter({hasText:'day-first or month-first'});
  await expect(dates).toContainText('2026-04-03 · -117.70 · Current account · Charges with GST');
  await expect(dates.getByRole('button', {name:'Mark as Done'})).toHaveCount(0);
  await expect(page.getByRole('button', {name:/Refresh/})).toHaveCount(0);
  for (const theme of ['minkops-light','minkops-dark','slate-light','slate-dark']) {
    await page.getByRole('combobox', {name:'Theme',exact:true}).selectOption(theme);
    await page.screenshot({path:testInfo.outputPath(`layout-questions-${theme}.png`)});
  }
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('layout-questions-mobile.png')});
  await page.getByRole('button',{name:'Day first',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Confirmed; waiting work continues');
  await expect(page.getByRole('button',{name:'Day first',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Do nothing',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Left for manual handling');
  await page.getByRole('button',{name:'Mark as Done',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Marked done');
  expect(decisions).toEqual([{action:'dmy'},{action:'nothing'}]);
  await expect(page.getByText('No items',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});
