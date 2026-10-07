/** Explicit release verification: owned demo tenant and isolated Test Company.
 * Never runs in CI. The save phase accepts only the reviewed synthetic RC bill.
 * Credentials and pairing state stay in the operator-supplied private directory.
 */
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { discoverTally, inspectExcel, inventory, excelSchemaBytes, tallyProbe, commitTallyBill, readTallyBills } from '../../../connectors/desktop/src/index.js';
import { collectSources } from '../../../platform/desktop-runtime/src/discovery.js';
import { CompanionWorker } from '../../../platform/desktop-runtime/src/worker.js';

const directory = process.env.MINKOPS_RELEASE_STATE;
const company = process.env.MINKOPS_TEST_COMPANY;
const phase = process.env.MINKOPS_RELEASE_PHASE || 'schema';
assert.ok(['schema', 'references', 'save'].includes(phase));
assert.ok(directory && company, 'Supply a private state directory and explicit test company');
const credentials = JSON.parse(await readFile(join(directory, 'demo-owner.json'), 'utf8'));
const origin = 'https://app.minkops.com';
let cookie = '', csrf = '', pending = null, executedJob = null, lastReceipt = null;
async function api(path, body, { method = body === undefined ? 'GET' : 'POST', worker = false } = {}) {
  const response = await fetch(origin + path, {
    method, redirect: 'error', signal: AbortSignal.timeout(65000),
    headers: { 'Content-Type': 'application/json', ...(worker ? { Authorization: `Bearer ${device.credential}` } : { Cookie: cookie, 'x-csrf-token': csrf }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = new Error(`Production HTTP ${response.status} at ${path}`);
    error.status = response.status;
    throw error;
  }
  if (response.headers.get('set-cookie')) cookie = response.headers.get('set-cookie').split(';')[0];
  return response.json();
}
await api('/api/auth/login', credentials);
const user = await api('/api/auth/me');
csrf = user.csrf_token;
assert.ok(user.memberships.some(m => m.slug === 'mock-tenant' && m.role === 'admin'));
assert.ok((await tallyProbe()).companies.includes(company), 'Explicit test company must be open');
const base = '/api/tenants/mock-tenant';
const device = phase === 'schema'
  ? await api(base + '/desktop/devices', { name: 'Production release verification PC', installation_id: randomUUID() })
  : JSON.parse(await readFile(join(directory, 'release-pc.json'), 'utf8'));
await writeFile(join(directory, 'release-pc.json'), JSON.stringify(device), { mode: 0o600 });
const run = phase === 'schema' ? await api(base + '/discovery/runs', {
  device_id: device.id, request_key: randomUUID(),
  config: { depth: 'structure', destination_mode: 'tally', excel_source_ids: [],
    tally: { company, port: 9000, categories: ['company','groups','ledgers','voucher_types','stock_items','stock_groups','units','godowns','cost_centres','cost_categories','currencies'] } },
}) : null;
const worker = new CompanionWorker({
  request: (path, body) => api(path, body, { worker: true }),
  pending: () => pending,
  savePending: async value => {
    pending = value;
    if (value) lastReceipt = value;
    await writeFile(join(directory, 'release-receipt.json'), JSON.stringify(value), { mode: 0o600 });
  },
  execute: async job => {
    executedJob = job;
    assert.equal(job.operation, { schema: 'sources.discover', references: 'tally.references', save: 'tally.save' }[phase]);
    const plan = await api(`/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`, undefined, { worker: true });
    if (phase === 'references') {
      assert.equal(plan.company, company);
      return discoverTally(plan);
    }
    if (phase === 'save') {
      assert.equal(company, 'Test Company');
      assert.equal(plan.company, company);
      assert.equal(plan.operation, 'append');
      assert.deepEqual(plan.data, {
        tax: 7056, date: '2026-10-01', total: 32256,
        vendor: 'RC Deccan Cement Traders', subtotal: 25200, cost_code: null,
        tax_ledger: 'RC Input GST Mock', invoice_number: 'RC26-CEM-041',
        purchase_ledger: 'RC Civil Materials Purchase',
      });
      let imports = 0;
      const request = (url, options) => {
        if (options.body.includes('<TALLYREQUEST>Import Data</TALLYREQUEST>')) imports++;
        return fetch(url, options);
      };
      const result = await commitTallyBill(plan, { request });
      assert.ok(['saved', 'duplicate'].includes(result.outcome));
      assert.ok(imports <= 1);
      const beforeReplay = imports;
      const replay = await commitTallyBill(plan, { request });
      assert.equal(replay.outcome, 'duplicate');
      assert.equal(imports, beforeReplay, 'Replay must perform no second import');
      const vouchers = (await readTallyBills(plan)).filter(v =>
        v.invoice_number === plan.data.invoice_number && v.vendor === plan.data.vendor && v.date === '20261001');
      assert.equal(vouchers.length, 1);
      console.log(JSON.stringify({ productionTallyReadback: 'passed', outcome: result.outcome, matchingVouchers: 1, replayImports: 0 }));
      return result;
    }
    return collectSources(plan, { inventory, inspectExcel, excelSchemaBytes, discoverTally,
      folderFor: () => { throw new Error('This schema check grants no folders'); },
      onProgress: (source_key,status,category=null) => api(`/api/desktop/worker/jobs/${job.id}/progress`, { claim_token: job.claim_token, source_key,status,category }, { worker: true }),
    });
  },
});
await worker.tick();
assert.ok(executedJob, 'Expected a native job; idle polling is not proof');
const completedJob = await api(base + `/desktop/jobs/${executedJob.id}`);
assert.equal(completedJob.state, 'completed');
await api(`/api/desktop/worker/jobs/${lastReceipt.id}/finish`, lastReceipt.receipt, { worker: true });
if (run) {
let detail = await api(base + `/discovery/runs/${run.id}`);
assert.equal(detail.catalog.partial, false);
if (detail.state === 'review')
  detail = await api(base + `/discovery/runs/${run.id}/confirm`, {});
assert.equal(detail.state, 'completed');
assert.equal(detail.ready, true);
const snapshot = detail.catalog.sources.find(s => s.tool === 'tally').snapshot;
assert.ok(snapshot.schema_tables.length > 0);
assert.ok(snapshot.collections.every(c => c.records.length === 0));
await writeFile(join(directory, 'production-schema.json'), JSON.stringify(detail.catalog, null, 2), { mode: 0o600 });
console.log(JSON.stringify({ productionSourceDiscovery: 'passed', run: run.id, tables: snapshot.schema_tables.length, businessRecords: 0, reviewed: true }));
} else {
  console.log(JSON.stringify({ operation: executedJob.operation, productionReceipt: 'accepted and replayed' }));
}
await api('/api/auth/logout', {});
