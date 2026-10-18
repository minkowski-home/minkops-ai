/* global URL, document, window */
import { test, expect } from '@playwright/test';

test('mixed runs show exceptions, saved counts, reasons and an authenticated CSV download', async ({ page, context }, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  let state = 'review';
  const record = (status, invoice) => ({ source_file_id: 'multi', status, operation: 'append', data: { invoice_number: invoice, total: 118 }, findings: [], evidence: [] });
  const rows = [
    { source_file_id: 'multi', source_file: 'multi.pdf', record_index: 2, status: 'Save held', reason: 'Tally rejected this bill and its destination settings need attention.' },
    { source_file_id: 'blank', source_file: 'blank.pdf', record_index: null, status: 'Not written (Do nothing)', reason: 'This source does not contain a bill that can be entered.' },
  ];
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({ body: '', contentType: 'text/css' }));
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body;
    if (path === '/api/auth/session') body = { id: 'user', name: 'QA', memberships: [{ slug: 'mock-tenant', role: 'admin' }], csrf_token: 'csrf' };
    else if (path.endsWith('/workspace')) body = { tenant: { slug: 'mock-tenant', name: 'QA' }, can_edit: true, employees: [], workflows: [], tasks: [] };
    else if (path.endsWith('/discovery/tasks/task')) body = null;
    else if (path.endsWith('/accounts/tasks/task/run')) body = {
      id: 'run', actor_id: 'user', task_id: 'task', workflow_key: 'bill-entry', state,
      config: { file_provenance: [{ id: 'multi', path: 'multi.pdf' }, { id: 'blank', path: 'blank.pdf' }] },
      result: { records: [record('saved', 'SAVED-1'), record('duplicate', 'EXISTING-1'), { ...record('held', 'HELD-1'), save_hold: 'diagnostic' }],
        findings: [], deferred: [{ source_file_id: 'blank' }] }, writes: [], tally_writes: [],
      review: { saved: 1, duplicates: 1, rows, export_unavailable: state === 'writing' ? 'Export is ready after destination saves have finished.' : null },
    };
    else if (path.endsWith('/unsaved-bills.csv')) {
      await route.fulfill({ body: '\ufeffSource file,Invoice number\r\nmulti.pdf,HELD-1\r\n', contentType: 'text/csv; charset=utf-8', headers: { 'Content-Disposition': 'attachment; filename="unsaved-bills-run.csv"' } });
      return;
    } else if (path.includes('/tasks/task')) body = { id: 'task', title: 'Bill entry', status: 'attention', progress: 0, events: [] };
    else throw new Error(`Unexpected ${path}`);
    await route.fulfill({ json: body });
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/tasks/task');
  await expect(page.getByText('1 saved · 1 already in Tally')).toBeVisible();
  await expect(page.locator('.accounts-bill')).toHaveCount(2);
  await expect(page.locator('.accounts-bill').getByText('SAVED-1')).toHaveCount(0);
  await expect(page.getByText(rows[0].reason)).toBeVisible();
  await expect(page.getByText(rows[1].reason)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry save', exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('unsaved-bills-run.csv');
  await page.screenshot({ path: testInfo.outputPath('bill-review-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('bill-review-mobile.png') });
  state = 'writing'; await page.reload();
  await expect(page.getByRole('button', { name: 'Export CSV' })).toBeDisabled();
  await expect(page.getByText('Export is ready after destination saves have finished.')).toBeVisible();
  expect(errors).toEqual([]);
});
