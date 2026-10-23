/* global URL, document, window */
import {test, expect} from '@playwright/test';

const pc = {id:'pc-1', name:'Shared server', owner_id:'qa', revoked_at:null, expires_at:'2099-01-01T00:00:00Z',
  last_seen_at:null, companion_version:'0.11.0', hostname:'HOST-7', remote_session:true, tally_port:9000};

test('a PC keeps its own Tally port, as each user on a shared server must', async ({page, context}, testInfo) => {
  const saved = [];
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path === '/api/auth/session')
      return route.fulfill({json:{id:'qa', name:'QA', memberships:[{slug:'mock-tenant', role:'member'}], csrf_token:'csrf'}});
    if (path.endsWith('/workspace'))
      return route.fulfill({json:{tenant:{slug:'mock-tenant', name:'QA'}, can_edit:false, employees:[], workflows:[], tasks:[]}});
    if (path === '/api/tenants/mock-tenant/desktop/devices') return route.fulfill({json:[pc]});
    if (path === '/api/tenants/mock-tenant/desktop/devices/pc-1' && request.method() === 'PATCH') {
      saved.push(request.postDataJSON());
      pc.tally_port = request.postDataJSON().tally_port;
      return route.fulfill({json:{device_id:'pc-1', tally_port:pc.tally_port}});
    }
    throw Error(`${request.method()} ${path}`);
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/connections');
  const card = page.getByRole('article').filter({hasText:'Shared server'});
  const port = card.getByRole('spinbutton', {name:'Tally port'});
  await expect(port).toHaveValue('9000');
  await port.fill('70000');
  await card.getByRole('button', {name:'Save port'}).click();
  // The browser refuses a port outside 1–65535 before anything is sent.
  expect(saved).toEqual([]);
  await port.fill('9101');
  await card.getByRole('button', {name:'Save port'}).click();
  await expect(card.getByRole('status').filter({hasText:'Minkops reads Tally on port 9101 on this PC.'})).toBeVisible();
  expect(saved).toEqual([{tally_port:9101}]);
  await expect(port).toHaveValue('9101');
  await card.screenshot({path:testInfo.outputPath('pc-port.png')});
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('a PC reconnecting itself after a restart is not offered as a new connection', async ({page, context}) => {
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/session')
      return route.fulfill({json:{id:'qa', name:'QA', memberships:[{slug:'mock-tenant', role:'member'}], csrf_token:'csrf'}});
    if (path.endsWith('/workspace'))
      return route.fulfill({json:{tenant:{slug:'mock-tenant', name:'QA'}, can_edit:false, employees:[], workflows:[], tasks:[]}});
    if (path === '/api/tenants/mock-tenant/desktop/devices') return route.fulfill({json:[pc]});
    throw Error(`${route.request().method()} ${path}`);
  });
  // The desktop app's bridge, as companion 0.11.1 reports a PC whose saved credential could not be read.
  await page.addInitScript(() => {
    const connects = [];
    window.connects = connects;
    window.minkopsDesktop = {version:1, status: async () => ({version:'0.11.1', name:'GAUSS-PC', device:null, reconnecting:true}),
      connect: async (tenant) => { connects.push(tenant); return {id:'pc-1'}; }, disconnect: async () => {}};
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/connections');
  const card = page.getByRole('article').filter({hasText:'GAUSS-PC'});
  await expect(card.getByText('Reconnecting this PC to your workspace…')).toBeVisible();
  await expect(card.getByRole('button', {name:'Connect this PC'})).toBeDisabled();
  expect(await page.evaluate(() => window.connects)).toEqual([]);
});
