/* global URL, document, window */
import { test, expect } from '@playwright/test';
import fs from 'node:fs';

const schema = JSON.parse(fs.readFileSync(new URL('../../../../employees/accounts-desk/workflows/bill-entry/tenant-config.schema.json', import.meta.url)));
const companies = [
  { company: 'Sachin Infra (2025-26)', company_guid: 'a', purchase_voucher_types: { default: 'purchase-a', candidates: [{ name: 'Purchase', guid: 'purchase-a', used: 12 }] } },
  { company: 'Sachin Infra (2026-27)', company_guid: 'b', purchase_voucher_types: { default: 'gst', candidates: [
    { name: 'Purchase', guid: 'purchase-b', used: 3 }, { name: 'Purchase GST', guid: 'gst', used: 41 }] } },
];
const target = {
  device_id: 'pc', company_mode: 'locked', locked_company_guid: 'b', voucher_type_version: 1,
  companies: [
    { company: 'Sachin Infra (2025-26)', references: { company_guid: 'a' }, voucher_type: { NAME: 'Purchase' } },
    { company: 'Sachin Infra (2026-27)', references: { company_guid: 'b' }, voucher_type: { NAME: 'Purchase GST' } },
  ],
};
const record = {
  source_file_id: 'bill-file', destination_file_id: 'discovery', sheet: 'Purchase', operation: 'append', company_guid: 'b',
  data: { vendor: 'Ultratech Cement Ltd', invoice_number: 'UC/2026/104', date: '2026-10-01', purchase_ledger: 'Cement Purchases',
    subtotal: 100000, tax: 18000, tax_ledger: null, total: 118000, cost_code: null },
  tax_allocations: [{ ref: 'r1', ledger: 'Input CGST 9%', amount: 9000, evidence: '' }, { ref: 'r2', ledger: 'Input SGST 9%', amount: 9000, evidence: '' }],
  evidence: [], findings: [], decision: 'approve',
};

test('a Tally run chooses its company and purchase voucher type, and shows what it will enter', async ({ page, context }, testInfo) => {
  const runs = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({ body: '', contentType: 'text/css' }));
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    let body = null;
    if (path === '/api/auth/session') body = { id: 'user', name: 'QA', email: 'qa@example.test', memberships: [{ slug: 'mock-tenant', role: 'admin' }], csrf_token: 'csrf' };
    else if (path.endsWith('/workspace')) body = { tenant: { slug: 'mock-tenant', name: 'Synthetic QA' }, can_edit: true, employees: [], tasks: [], workflows: [
      { id: 'bill', key: 'bill-entry', name: 'Bill entry', status: 'active', employee_ids: [], presentation: 'accounts-bill', config_schema: schema,
        config_values: { output_mode: 'tally_in_place', input_format: 'mixed', review_mode: 'only_exceptions', company_mode: 'locked' } }] };
    else if (path.endsWith('/desktop/devices')) body = [{ id: 'pc', name: 'PRAHLAD-GADHWAL', owner_id: 'user', revoked_at: null, expires_at: '2099-01-01',
      last_seen_at: new Date().toISOString(), companion_version: '0.7.0', hostname: 'PRAHLAD-GADHWAL', remote_session: false }];
    else if (path.endsWith('/discovery/latest')) body = { id: 'discovery', ready: true, device_id: 'pc', config: { tally: {} }, catalog: { sources: [{ tool: 'tally', snapshot: { companies } }] } };
    else if (path.endsWith('/accounts/sources')) body = [{ id: 'upload', label: 'Bills', writable: false, files: [{ id: 'bill-file', path: 'ultratech-104.pdf', sha256: 'x' }] }];
    else if (path.endsWith('/accounts/catalogs')) body = [];
    else if (path.endsWith('/accounts/runs') && method === 'POST') { runs.push(request.postDataJSON()); body = { task_id: 'task' }; }
    else if (path.endsWith('/discovery/tasks/task')) body = null;
    else if (path.endsWith('/accounts/tasks/task/run')) body = { id: 'run', actor_id: 'user', task_id: 'task', workflow_key: 'bill-entry', state: 'review',
      config: { tally_target: target, file_provenance: [{ id: 'bill-file', path: 'ultratech-104.pdf' }] }, result: { records: [record], findings: [] }, writes: [], tally_writes: [], error: null };
    else if (path.includes('/tasks/task')) body = { id: 'task', title: 'Bill entry', workflow_id: 'bill', status: 'attention', progress: 0, events: [] };
    else throw new Error(`Unhandled ${method} ${path}`);
    await route.fulfill({ json: body });
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/workflows/bill');
  const run = page.getByRole('button', { name: 'Run bill entry', exact: true });
  await page.getByRole('checkbox', { name: /ultratech-104\.pdf/ }).check();
  const company = page.getByLabel('Company for all bills', { exact: true });
  await expect(company).toHaveValue('', { timeout: 10000 });
  await expect(page.getByText('Choose the company these bills belong to.')).toBeVisible();
  await expect(run).toBeDisabled();
  await company.selectOption('a');
  await expect(page.getByLabel(/Purchase voucher type for/)).toHaveCount(0);  // one type: no question
  await expect(run).toBeEnabled();
  await company.selectOption('b');
  const voucherType = page.getByLabel('Purchase voucher type for Sachin Infra (2026-27)', { exact: true });
  await expect(voucherType).toHaveValue('gst');
  await expect(voucherType.getByRole('option', { name: 'Purchase GST · used 41 times' })).toHaveCount(1);
  await page.getByLabel('Tally destination').scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('tally-launch.png') });
  await voucherType.selectOption('');
  await expect(page.getByText('Choose the purchase voucher type for Sachin Infra (2026-27).')).toBeVisible();
  await expect(run).toBeDisabled();
  await voucherType.selectOption('purchase-b');
  await run.click();
  await page.waitForURL('**/tasks/task');
  expect(runs.at(-1).config).toMatchObject({ company_mode: 'locked', locked_company_guid: 'b', purchase_voucher_types: { b: 'purchase-b' } });

  await page.getByRole('button', { name: 'Show details' }).click();
  const details = page.getByRole('dialog', { name: 'Details for ultratech-104.pdf' });
  await expect(details).toBeVisible();
  await expect(details.getByText('Will be entered in Tally')).toBeVisible();
  for (const text of ['Sachin Infra (2026-27)', 'Purchase GST', '1 Oct 2026', 'Ultratech Cement Ltd', 'UC/2026/104', 'Cement Purchases', '1,00,000.00', 'Input CGST 9%', '1,18,000.00'])
    await expect(details.getByText(text, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('bill-details-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath('bill-details-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.keyboard.press('Escape');
  await expect(details).toBeHidden();
  await expect(page.getByRole('button', { name: 'Write bill' })).toBeVisible();
  expect(errors).toEqual([]);
});
