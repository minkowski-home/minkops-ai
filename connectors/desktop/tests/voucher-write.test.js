import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyRejection, saveVoucher, readVouchers, validatePlan, voucherFamilies} from '../src/voucher.js';
import {TallyUnavailable} from '../src/tally-session.js';

const id = '12345678-1234-5234-8234-123456789abc';
const ledgers = ['Supplier A', 'Purchase 18%', 'Input CGST', 'Input SGST', 'Round Off', 'HDFC', 'ICICI', 'Bank Charges'];
const references = {company_guid: 'company', ledgers: Object.fromEntries(ledgers.map(name => [name, {GUID: `${name}-guid`, PARENT: 'Group', ALTERID: '12'}]))};
const site = {category: 'Sites', category_guid: 'cat', centre: 'Site 4', centre_guid: 'cc'};

const purchase = {
  format_version: 5, family: 'purchase', operation: 'append', company: 'Test', company_guid: 'company', port: 9000,
  remote_id: id, voucher_type: {NAME: 'Purchase GST', GUID: 'vt-purchase'},
  header: {date: '2026-10-01', reference: 'INV-17', party_ledger: 'Supplier A', narration: 'Minkops reviewed bill INV-17', tag: null},
  lines: [
    {ledger: 'Supplier A', side: 'credit', amount_cents: 118040, allocation: null},
    {ledger: 'Purchase 18%', side: 'debit', amount_cents: 100000, allocation: site},
    {ledger: 'Input CGST', side: 'debit', amount_cents: 9000, allocation: null},
    {ledger: 'Input SGST', side: 'debit', amount_cents: 9000, allocation: null},
    {ledger: 'Round Off', side: 'debit', amount_cents: 40, allocation: null},
  ],
  references,
  duplicate: {strategy: 'document', families: ['purchase', 'journal'], party_ledger: 'Supplier A', number: 'INV-17',
    number_fields: ['REFERENCE'], window: {from: '2026-04-01', to: '2027-03-31'}},
  fence: 'retry_after_read', expected: null,
};
const payment = {
  ...purchase, family: 'payment', voucher_type: {NAME: 'Payment', GUID: 'vt-payment'},
  header: {date: '2026-10-01', reference: 'UTR1', party_ledger: null, narration: 'NEFT charges', tag: 'statement'},
  lines: [{ledger: 'HDFC', side: 'credit', amount_cents: 1770, allocation: null}, {ledger: 'Bank Charges', side: 'debit', amount_cents: 1770, allocation: null}],
  duplicate: {strategy: 'tag', window: {from: '2026-10-01', to: '2026-10-01'}, match: {ledger: 'HDFC', side: 'credit', amount_cents: 1770}, distinct: []},
  fence: 'strict',
};
const contra = {
  ...payment, family: 'contra', voucher_type: {NAME: 'Contra', GUID: 'vt-contra'},
  header: {...payment.header, narration: 'Transfer to ICICI'},
  lines: [{ledger: 'HDFC', side: 'credit', amount_cents: 500000, allocation: null}, {ledger: 'ICICI', side: 'debit', amount_cents: 500000, allocation: null}],
  duplicate: {strategy: 'counterpart', window: {from: '2026-09-28', to: '2026-10-04'}, match: {ledger: 'HDFC', side: 'credit', amount_cents: 500000}, distinct: []},
};

const types = [
  {NAME: 'Purchase', '@_RESERVEDNAME': 'Purchase', GUID: 'p'}, {NAME: 'Purchase GST', PARENT: 'Purchase', GUID: 'vt-purchase'},
  {NAME: 'Journal', '@_RESERVEDNAME': 'Journal', GUID: 'j'}, {NAME: 'Debit Note', '@_RESERVEDNAME': 'Debit Note', GUID: 'vt-dn'},
  {NAME: 'Payment', '@_RESERVEDNAME': 'Payment', GUID: 'vt-payment'}, {NAME: 'Contra', '@_RESERVEDNAME': 'Contra', GUID: 'vt-contra'},
];
const stockRecords = [{NAME: 'Cement', GUID: 'item-cement', BASEUNITS: 'Bag', ISBATCHWISEON: 'No'}];
const godownRecords = [{NAME: 'Main Location', GUID: 'gd-main'}, {NAME: 'Site Store', GUID: 'gd-site'}];
const snapshot = ({ledgerRecords, typeRecords = types, centres = [{NAME: 'Site 4', GUID: 'cc'}], items = stockRecords,
  godowns = godownRecords} = {}) => ({collections: [
  {category: 'company', status: 'ready', records: [{GUID: 'company', ISCOSTCENTRESON: 'Yes'}]},
  {category: 'ledgers', status: 'ready', records: ledgerRecords ?? ledgers.map(NAME => ({NAME, GUID: `${NAME}-guid`, PARENT: 'Group', ALTERID: ' 12 ', ISCOSTCENTRESON: 'Yes'}))},
  {category: 'voucher_types', status: 'ready', records: typeRecords},
  {category: 'cost_centres', status: 'ready', records: centres.map(c => ({CATEGORY: 'Sites', ...c}))},
  {category: 'cost_categories', status: 'ready', records: [{NAME: 'Sites', GUID: 'cat'}]},
  {category: 'stock_items', status: 'ready', records: items},
  {category: 'godowns', status: 'ready', records: godowns},
]});
const signed = line => line.side === 'credit' ? line.amount_cents : -line.amount_cents;
/** The voucher Tally would return for exactly this plan. */
const observed = (plan, overrides = {}) => ({
  guid: 'a1b2c3d4-0000-4000-8000-000000000007', master_id: '7', date: plan.header.date.replaceAll('-', ''), voucher_type: plan.voucher_type.NAME,
  reference: plan.header.reference ?? '', number: '', party_ledger: plan.header.party_ledger ?? '',
  narration: plan.header.tag ? `[Minkops ${plan.header.tag}:${plan.remote_id}] ${plan.header.narration}` : plan.header.narration,
  tag: plan.header.tag ? plan.remote_id : null, unsupported: false, fingerprint: 'v5:existing',
  entries: plan.lines.map(l => ({ledger: l.ledger, amount_cents: signed(l)})).sort((a, b) => a.ledger.localeCompare(b.ledger) || a.amount_cents - b.amount_cents),
  allocations: plan.lines.filter(l => l.allocation).map(l => ({ledger: l.ledger, category: l.allocation.category, centre: l.allocation.centre, amount_cents: signed(l)})),
  bills: plan.lines.flatMap(l => (l.bills ?? []).map(b => ({ledger: l.ledger, name: b.name ?? null, type: b.type,
    amount_cents: l.side === 'credit' ? b.amount_cents : -b.amount_cents}))),
  inventory: (plan.inventory ?? []).map(e => ({item: e.item, unit: e.unit, quantity: e.quantity, rate: e.rate,
    amount_cents: -e.amount_cents, ledger: e.ledger,
    godowns: e.godowns.map(g => ({godown: g.godown, quantity: g.quantity, amount_cents: -g.amount_cents}))})),
  ...overrides,
});
const accepted = '<RESPONSE><CREATED>1</CREATED><ALTERED>0</ALTERED><ERRORS>0</ERRORS></RESPONSE>';

/** Native fakes: `reads` are successive voucher reads; imports are recorded. */
function harness(reads, {reply = accepted, references: refs = snapshot(), fence = async () => true} = {}) {
  const io = {imports: [], reads: 0, companyChecks: 0};
  io.options = {
    requireCompany: async () => { io.companyChecks++; },
    readReferences: async () => refs,
    readVouchers: async () => reads[Math.min(io.reads++, reads.length - 1)] ?? [],
    beforeImport: async intent => { assert.equal(io.imports.length, 0); return fence(intent); },
    request: async (_url, {body}) => {
      io.imports.push(body);
      if (reply instanceof Error) throw reply;
      return new Response(reply);
    },
  };
  return io;
}

test('plans are validated before any native call', async () => {
  const bad = [
    {...purchase, format_version: 4},
    {...purchase, family: 'sales'},
    {...purchase, lines: purchase.lines.slice(0, 1)},
    {...purchase, lines: [...purchase.lines.slice(0, 4), {...purchase.lines[4], amount_cents: 41}]},
    {...purchase, lines: [...purchase.lines, ...Array.from({length: 36}, () => purchase.lines[4])]},
    {...purchase, lines: [...purchase.lines.slice(0, 3), {...purchase.lines[2], amount_cents: 9040}]},
    {...purchase, lines: purchase.lines.map(l => ({...l, side: l.side === 'credit' ? 'debit' : 'credit'}))},
    {...purchase, header: {...purchase.header, party_ledger: 'Somebody'}},
    {...purchase, references: {...references, ledgers: {...references.ledgers, 'Round Off': undefined}}},
    {...purchase, duplicate: {...purchase.duplicate, window: {from: '2026-10-02', to: '2027-03-31'}}},
    {...purchase, duplicate: {...purchase.duplicate, window: {from: '2025-04-01', to: '2027-03-31'}}},
    {...purchase, duplicate: {...purchase.duplicate, number_fields: ['PARTYLEDGERNAME']}},
    {...purchase, duplicate: {...purchase.duplicate, families: ['journal']}},
    {...purchase, operation: 'update'},
    {...purchase, fence: 'none'},
    {...purchase, lines: purchase.lines.map((l, i) => i === 1 ? {...l, allocation: {...site, centre_guid: ''}} : l)},
    {...payment, header: {...payment.header, tag: null}},
    {...payment, duplicate: {...payment.duplicate, match: {ledger: 'HDFC', side: 'debit', amount_cents: 1770}}},
    {...payment, duplicate: {...contra.duplicate, match: payment.duplicate.match}},
    {...payment, remote_id: 'not-a-uuid'},
  ];
  for (const plan of bad) {
    const io = harness([[]]);
    await assert.rejects(saveVoucher(plan, io.options), /Unsupported voucher plan/);
    assert.equal(io.companyChecks + io.imports.length, 0);
  }
  assert.equal(validatePlan(purchase), purchase);
});

test('one import carries every line with native signs, allocations and the pinned voucher type', async () => {
  const io = harness([[], [observed(purchase)]]);
  const result = await saveVoucher(purchase, io.options);
  assert.equal(result.outcome, 'saved');
  assert.equal(result.current.family, 'purchase');
  assert.equal(result.current.narration, 'Minkops reviewed bill INV-17');
  assert.equal(io.imports.length, 1);
  const body = io.imports[0];
  for (const fragment of [
    `REMOTEID="${id}" Action="Create" VCHTYPE="Purchase GST"`,
    '<VOUCHERTYPENAME>Purchase GST</VOUCHERTYPENAME><REFERENCE>INV-17</REFERENCE><PARTYLEDGERNAME>Supplier A</PARTYLEDGERNAME>',
    '<LEDGERNAME>Supplier A</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>1180.40</AMOUNT>',
    '<LEDGERNAME>Purchase 18%</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-1000.00</AMOUNT><CATEGORYALLOCATIONS.LIST><CATEGORY>Sites</CATEGORY>',
    '<COSTCENTREALLOCATIONS.LIST><NAME>Site 4</NAME><AMOUNT>-1000.00</AMOUNT>',
    '<LEDGERNAME>Round Off</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-0.40</AMOUNT>',
    '<NARRATION>Minkops reviewed bill INV-17</NARRATION>',
  ]) assert.ok(body.includes(fragment), fragment);
  // A replay after a lost acknowledgement reads the saved voucher and never imports.
  const replay = harness([[observed(purchase)]]);
  assert.equal((await saveVoucher(purchase, replay.options)).outcome, 'duplicate');
  assert.equal(replay.imports.length, 0);
});

test('disabled or regrouped cost allocations hold before importing a voucher', async () => {
  for (const change of ['company disabled', 'ledger disabled', 'centre regrouped']) {
    const refs = snapshot();
    if (change === 'company disabled') refs.collections[0].records[0].ISCOSTCENTRESON = 'No';
    if (change === 'ledger disabled') refs.collections[1].records.find(r => r.NAME === 'Purchase 18%').ISCOSTCENTRESON = 'No';
    if (change === 'centre regrouped') refs.collections[3].records[0].CATEGORY = 'Another category';
    const io = harness([[], [observed(purchase)]], {references: refs});
    const result = await saveVoucher(purchase, io.options);
    assert.equal(result.hold, 'destination_changed', change);
    assert.equal(io.imports.length, 0, change);
  }
});

// Protocol 6: a bill-by-bill ledger's line carries its bill references.
const billed = {...purchase, format_version: 6,
  lines: purchase.lines.map((l, i) => i === 0 ? {...l, bills: [{name: 'INV-17', type: 'New Ref', amount_cents: 118040}]} : l)};
const settling = {...payment, format_version: 6, lines: [
  {ledger: 'HDFC', side: 'credit', amount_cents: 150000, allocation: null},
  {ledger: 'Supplier A', side: 'debit', amount_cents: 150000, allocation: null, bills: [
    {name: 'INV-17', type: 'Agst Ref', amount_cents: 118040}, {name: null, type: 'On Account', amount_cents: 31960}]}],
  duplicate: {...payment.duplicate, match: {ledger: 'HDFC', side: 'credit', amount_cents: 150000}}};

test('bill references are written with their ledger line, in native signs, and required on readback', async () => {
  const io = harness([[], [observed(billed)]]);
  assert.equal((await saveVoucher(billed, io.options)).outcome, 'saved');
  assert.ok(io.imports[0].includes('<LEDGERNAME>Supplier A</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>1180.40</AMOUNT>'
    + '<BILLALLOCATIONS.LIST><NAME>INV-17</NAME><BILLTYPE>New Ref</BILLTYPE><AMOUNT>1180.40</AMOUNT></BILLALLOCATIONS.LIST>'));
  const payments = harness([[], [observed(settling)]]);
  const paid = await saveVoucher(settling, payments.options);
  assert.equal(paid.outcome, 'saved');
  assert.deepEqual(paid.current.bills, [{ledger: 'Supplier A', name: 'INV-17', type: 'Agst Ref', amount_cents: -118040},
    {ledger: 'Supplier A', name: null, type: 'On Account', amount_cents: -31960}]);
  assert.ok(payments.imports[0].includes('<BILLALLOCATIONS.LIST><NAME>INV-17</NAME><BILLTYPE>Agst Ref</BILLTYPE><AMOUNT>-1180.40</AMOUNT>'
    + '</BILLALLOCATIONS.LIST><BILLALLOCATIONS.LIST><BILLTYPE>On Account</BILLTYPE><AMOUNT>-319.60</AMOUNT></BILLALLOCATIONS.LIST>'));
  // A readback missing the reference is not the approved voucher.
  const lost = harness([[], [observed(billed, {bills: []})]]);
  assert.equal((await saveVoucher(billed, lost.options)).hold, 'uncertain_import');
  const bad = [
    {...purchase, lines: billed.lines},
    {...billed, lines: billed.lines.map((l, i) => i === 0 ? {...l, bills: [{name: 'INV-17', type: 'New Ref', amount_cents: 100}]} : l)},
    {...billed, lines: billed.lines.map((l, i) => i === 0 ? {...l, bills: [{name: 'INV-17', type: 'Credit', amount_cents: 118040}]} : l)},
    {...billed, lines: billed.lines.map((l, i) => i === 0 ? {...l, bills: [{type: 'New Ref', amount_cents: 118040}]} : l)},
    {...settling, lines: settling.lines.map((l, i) => i === 1 ? {...l, bills: [{name: 'X', type: 'On Account', amount_cents: 150000}]} : l)},
  ];
  for (const plan of bad) await assert.rejects(saveVoucher(plan, harness([[]]).options), /Unsupported voucher plan/);
});

// Protocol 6: a purchase booked item-wise; its purchase ledger line carries the items' value.
const stocked = {...purchase, format_version: 6,
  lines: [{ledger: 'Supplier A', side: 'credit', amount_cents: 118000, allocation: null},
    {ledger: 'Purchase 18%', side: 'debit', amount_cents: 100000, allocation: null},
    {ledger: 'Input CGST', side: 'debit', amount_cents: 9000, allocation: null},
    {ledger: 'Input SGST', side: 'debit', amount_cents: 9000, allocation: null}],
  inventory: [{item: 'Cement', unit: 'Bag', quantity: '2.5', rate: '400', side: 'debit', amount_cents: 100000, ledger: 'Purchase 18%',
    godowns: [{godown: 'Main Location', quantity: '1.5', amount_cents: 60000}, {godown: 'Site Store', quantity: '1', amount_cents: 40000}]}],
  references: {...references, stock_items: {Cement: {GUID: 'item-cement', BASEUNITS: 'Bag'}},
    godowns: {'Main Location': {GUID: 'gd-main'}, 'Site Store': {GUID: 'gd-site'}}}};

test('an item-wise purchase is written in the invoice view with its godowns, and read back item by item', async () => {
  const io = harness([[], [observed(stocked)]]);
  const result = await saveVoucher(stocked, io.options);
  assert.equal(result.outcome, 'saved');
  assert.deepEqual(result.current.inventory[0].godowns[1], {godown: 'Site Store', quantity: '1', amount_cents: -40000});
  const body = io.imports[0];
  for (const fragment of [
    'VCHTYPE="Purchase GST" OBJVIEW="Invoice Voucher View"', '<PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW><ISINVOICE>Yes</ISINVOICE>',
    '<LEDGERENTRIES.LIST><LEDGERNAME>Supplier A</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>1180.00</AMOUNT></LEDGERENTRIES.LIST>',
    '<ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>Cement</STOCKITEMNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><RATE>400/Bag</RATE>'
      + '<ACTUALQTY>2.5 Bag</ACTUALQTY><BILLEDQTY>2.5 Bag</BILLEDQTY><AMOUNT>-1000.00</AMOUNT>',
    '<BATCHALLOCATIONS.LIST><GODOWNNAME>Main Location</GODOWNNAME><BATCHNAME>Primary Batch</BATCHNAME><AMOUNT>-600.00</AMOUNT>'
      + '<ACTUALQTY>1.5 Bag</ACTUALQTY><BILLEDQTY>1.5 Bag</BILLEDQTY></BATCHALLOCATIONS.LIST>',
    '<ACCOUNTINGALLOCATIONS.LIST><LEDGERNAME>Purchase 18%</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-1000.00</AMOUNT>',
  ]) assert.ok(body.includes(fragment), fragment);
  // The purchase ledger is written only inside its item, never as a ledger entry of its own.
  assert.ok(!body.includes('<LEDGERNAME>Purchase 18%</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-1000.00</AMOUNT></LEDGERENTRIES.LIST>'));
  // A readback whose stock went to another godown, or without the item, is not the approved voucher.
  const moved = observed(stocked);
  moved.inventory[0].godowns = [{godown: 'Main Location', quantity: '2.5', amount_cents: -100000}];
  for (const current of [moved, observed(stocked, {inventory: []})])
    assert.equal((await saveVoucher(stocked, harness([[], [current]]).options)).hold, 'uncertain_import');
  const bad = [
    {...stocked, format_version: 5},
    {...stocked, inventory: [{...stocked.inventory[0], side: 'credit'}]},
    {...stocked, inventory: [{...stocked.inventory[0], quantity: '2.50.1'}]},
    {...stocked, inventory: [{...stocked.inventory[0], ledger: 'Input CGST'}]},
    {...stocked, inventory: [{...stocked.inventory[0], godowns: [stocked.inventory[0].godowns[0]]}]},
    {...stocked, inventory: [{...stocked.inventory[0], godowns: stocked.inventory[0].godowns.map(g => ({...g, quantity: '1.2'}))}]},
    {...stocked, references: {...stocked.references, godowns: {'Main Location': {GUID: 'gd-main'}}}},
    {...stocked, family: 'journal', duplicate: {...stocked.duplicate, families: ['journal']}},
  ];
  for (const plan of bad) await assert.rejects(saveVoucher(plan, harness([[]]).options), /Unsupported voucher plan/);
  // A stock item recounted in another unit or now kept in batches, or a godown replaced, is not what the run read.
  for (const refs of [snapshot({items: [{...stockRecords[0], BASEUNITS: 'Kg'}]}), snapshot({items: [{...stockRecords[0], ISBATCHWISEON: 'Yes'}]}),
    snapshot({godowns: [godownRecords[0], {NAME: 'Site Store', GUID: 'other'}]})]) {
    const changed = harness([[]], {references: refs});
    assert.equal((await saveVoucher(stocked, changed.options)).hold, 'destination_changed');
    assert.equal(changed.imports.length, 0);
  }
});

test('a supplier credit note is a Debit Note with the party debited', async () => {
  const note = {...purchase, family: 'debit_note', voucher_type: {NAME: 'Debit Note', GUID: 'vt-dn'},
    lines: purchase.lines.map(l => ({...l, side: l.side === 'credit' ? 'debit' : 'credit'})),
    duplicate: {...purchase.duplicate, families: ['debit_note']}};
  const io = harness([[], [observed(note)]]);
  assert.equal((await saveVoucher(note, io.options)).outcome, 'saved');
  assert.ok(io.imports[0].includes('<LEDGERNAME>Supplier A</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-1180.40</AMOUNT>'));
  await assert.rejects(saveVoucher({...note, lines: purchase.lines}, harness([[]]).options), /party side/);
});

test('voucher reads are bounded to the calendar window and parsed into comparable records', async () => {
  const bodies = [];
  const reply = vouchers => async (_url, {body}) => {
    bodies.push(body);
    return new Response(`<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${vouchers}</COLLECTION></DATA></BODY></ENVELOPE>`);
  };
  const voucher = date => `<VOUCHER><MASTERID>7</MASTERID><GUID>g</GUID><DATE>${date}</DATE><VOUCHERNUMBER>12</VOUCHERNUMBER><REFERENCE>INV-17</REFERENCE>`
    + `<NARRATION>[Minkops statement:${id}] UPI</NARRATION><PARTYLEDGERNAME>Supplier A</PARTYLEDGERNAME><VOUCHERTYPENAME>Purchase GST</VOUCHERTYPENAME>`
    + '<ALLLEDGERENTRIES.LIST><LEDGERNAME>Supplier A</LEDGERNAME><AMOUNT>1180.40</AMOUNT></ALLLEDGERENTRIES.LIST>'
    + '<ALLLEDGERENTRIES.LIST><LEDGERNAME>Purchase 18%</LEDGERNAME><AMOUNT>-1180.40</AMOUNT><CATEGORYALLOCATIONS.LIST><CATEGORY>Sites</CATEGORY>'
    + '<COSTCENTREALLOCATIONS.LIST><NAME>Site 4</NAME><AMOUNT>-1180.40</AMOUNT></COSTCENTREALLOCATIONS.LIST></CATEGORYALLOCATIONS.LIST></ALLLEDGERENTRIES.LIST></VOUCHER>';
  const [record] = await readVouchers({company: 'Test', port: 9000, window: purchase.duplicate.window}, {request: reply(voucher('20261001'))});
  assert.ok(bodies[0].includes('<SVFROMDATE TYPE="Date">20260401</SVFROMDATE><SVTODATE TYPE="Date">20270331</SVTODATE>'));
  assert.ok(bodies[0].includes('$$DayOfDate:$Date) >= 20260401) AND (') && bodies[0].includes('&lt;= 20270331)'));
  assert.deepEqual({...record, fingerprint: undefined}, {
    guid: 'g', master_id: '7', date: '20261001', voucher_type: 'Purchase GST', reference: 'INV-17', number: '12',
    narration: `[Minkops statement:${id}] UPI`, party_ledger: 'Supplier A', tag: id, unsupported: false, fingerprint: undefined,
    entries: [{ledger: 'Purchase 18%', amount_cents: -118040}, {ledger: 'Supplier A', amount_cents: 118040}],
    allocations: [{ledger: 'Purchase 18%', category: 'Sites', centre: 'Site 4', amount_cents: -118040}], bills: [], inventory: [],
  });
  assert.match(record.fingerprint, /^v5:[a-f0-9]{64}$/);
  // Bill references are read with their ledger; they no longer make a voucher unsupported.
  const referenced = voucher('20261001').replace('<AMOUNT>1180.40</AMOUNT></ALLLEDGERENTRIES.LIST>',
    '<AMOUNT>1180.40</AMOUNT><BILLALLOCATIONS.LIST><NAME>INV-17</NAME><BILLTYPE>New Ref</BILLTYPE><AMOUNT>1180.40</AMOUNT>'
    + '</BILLALLOCATIONS.LIST></ALLLEDGERENTRIES.LIST>');
  const [withBills] = await readVouchers({company: 'Test', port: 9000, window: purchase.duplicate.window}, {request: reply(referenced)});
  assert.deepEqual([withBills.unsupported, withBills.bills],
    [false, [{ledger: 'Supplier A', name: 'INV-17', type: 'New Ref', amount_cents: 118040}]]);
  // Tally's own export of an item-wise purchase: each item with its godowns and the ledger that carries its value.
  const batch = (godown, qty, amount, order = ' Not Applicable') => `<BATCHALLOCATIONS.LIST><GODOWNNAME>${godown}</GODOWNNAME>`
    + `<BATCHNAME>Primary Batch</BATCHNAME><AMOUNT>${amount}</AMOUNT><ACTUALQTY>${qty} Bag</ACTUALQTY><BILLEDQTY>${qty} Bag</BILLEDQTY>`
    + `<ORDERNO>${order}</ORDERNO><TRACKINGNUMBER> Not Applicable</TRACKINGNUMBER></BATCHALLOCATIONS.LIST>`;
  const item = (order) => '<ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>Cement</STOCKITEMNAME><RATE>472.16/Bag</RATE>'
    + '<ACTUALQTY>2.500 Bag</ACTUALQTY><BILLEDQTY>2.500 Bag</BILLEDQTY><AMOUNT>-1180.40</AMOUNT>'
    + batch('Main Location', '1.500', '-708.24', order) + batch('Site Store', '1.000', '-472.16')
    + '<ACCOUNTINGALLOCATIONS.LIST><LEDGERNAME>Purchase 18%</LEDGERNAME><AMOUNT>-1180.40</AMOUNT></ACCOUNTINGALLOCATIONS.LIST>'
    + '</ALLINVENTORYENTRIES.LIST></VOUCHER>';
  const [stock] = await readVouchers({company: 'Test', port: 9000, window: purchase.duplicate.window}, {request: reply(voucher('20261001').replace('</VOUCHER>', item()))});
  assert.deepEqual([stock.unsupported, stock.inventory], [false, [{item: 'Cement', unit: 'Bag', quantity: '2.5', rate: '472.16',
    amount_cents: -118040, ledger: 'Purchase 18%', godowns: [{godown: 'Main Location', quantity: '1.5', amount_cents: -70824},
      {godown: 'Site Store', quantity: '1', amount_cents: -47216}]}]]);
  // Stock tracked against an order is more than a plan states.
  const [ordered] = await readVouchers({company: 'Test', port: 9000, window: purchase.duplicate.window}, {request: reply(voucher('20261001').replace('</VOUCHER>', item('PO-7')))});
  assert.equal(ordered.unsupported, true);
  await assert.rejects(readVouchers({company: 'Test', port: 9000, window: purchase.duplicate.window}, {request: reply(voucher('20270401'))}), /outside the requested window/);
});

test('document identity uses the client\'s number fields, with narration matched as a whole token', async () => {
  const plan = {...purchase, duplicate: {...purchase.duplicate, number_fields: ['REFERENCE', 'NARRATION']}};
  const inNarration = observed(plan, {reference: '', narration: 'Bill INV-17 received by site'});
  const io = harness([[inNarration]]);
  assert.equal((await saveVoucher(plan, io.options)).outcome, 'duplicate');
  assert.equal(io.imports.length, 0);
  const longer = harness([[observed(plan, {reference: '', narration: 'Bill INV-170 received'})], [observed(plan)]]);
  assert.equal((await saveVoucher(plan, longer.options)).outcome, 'saved');
  assert.equal(longer.imports.length, 1);
});

test('a document already booked in another family is never entered again', async () => {
  const io = harness([[observed(purchase, {voucher_type: 'Journal'})]]);
  const result = await saveVoucher(purchase, io.options);
  assert.equal(result.outcome, 'attention');
  assert.match(result.message, /already records this document as a Journal voucher/);
  assert.equal(io.imports.length, 0);
});

test('a different existing version is a correction until its approved fingerprint is supplied', async () => {
  const differing = observed(purchase, {entries: observed(purchase).entries.map(e => e.ledger === 'Round Off' ? {...e, amount_cents: -50} : e)});
  const first = harness([[differing]]);
  assert.equal((await saveVoucher(purchase, first.options)).outcome, 'correction');
  assert.equal(first.imports.length, 0);
  const approved = {...purchase, operation: 'update', expected: {fingerprint: 'v5:existing'}};
  const io = harness([[differing], [observed(purchase)]], {reply: '<RESPONSE><CREATED>0</CREATED><ALTERED>1</ALTERED><ERRORS>0</ERRORS></RESPONSE>'});
  assert.equal((await saveVoucher(approved, io.options)).outcome, 'saved');
  assert.ok(io.imports[0].includes('DATE="20261001" TAGNAME="MASTER ID" TAGVALUE="7" Action="Alter"'));
  const stale = harness([[{...differing, fingerprint: 'v5:edited-since'}]]);
  assert.equal((await saveVoucher(approved, stale.options)).outcome, 'correction');
  const inventory = harness([[{...differing, unsupported: true}]]);
  assert.match((await saveVoucher(approved, inventory.options)).message, /cannot preserve/);
  assert.equal(stale.imports.length + inventory.imports.length, 0);
});

test('statement tags: own tag is a duplicate; another voucher on that day holds unless proven distinct', async () => {
  assert.equal((await saveVoucher(payment, harness([[observed(payment)]]).options)).outcome, 'duplicate');
  const untagged = observed(payment, {tag: null, narration: 'manual entry'});
  assert.equal((await saveVoucher(payment, harness([[untagged]]).options)).hold, 'possible_existing');
  const other = '87654321-4321-5321-8321-cba987654321';
  const sibling = observed(payment, {tag: other});
  assert.equal((await saveVoucher(payment, harness([[sibling]]).options)).hold, 'possible_existing');
  const distinct = {...payment, duplicate: {...payment.duplicate, distinct: [other]}};
  const io = harness([[sibling], [sibling, observed(payment)]]);
  assert.equal((await saveVoucher(distinct, io.options)).outcome, 'saved');
  assert.equal(io.imports.length, 1);
  assert.ok(io.imports[0].includes(`<NARRATION>[Minkops statement:${id}] NEFT charges</NARRATION>`));
});

test('a lone Contra leg is covered by a transfer Minkops already entered, and an untagged one holds', async () => {
  const other = '87654321-4321-5321-8321-cba987654321';
  const earlier = observed(contra, {tag: other, date: '20260930'});
  const covered = await saveVoucher(contra, harness([[earlier]]).options);
  assert.equal(covered.outcome, 'duplicate');
  assert.equal(covered.covered, true);
  assert.equal((await saveVoucher(contra, harness([[{...earlier, tag: null}]]).options)).hold, 'possible_existing');
  const io = harness([[], [observed(contra)]]);
  assert.equal((await saveVoucher(contra, io.options)).outcome, 'saved');
  assert.equal(io.imports.length, 1);
});

test('strict fence: no import without the durable fence, and an uncertain import is only read back', async () => {
  const unfenced = harness([[]], {fence: async () => false});
  assert.equal((await saveVoucher(payment, unfenced.options)).hold, 'uncertain_import');
  assert.equal(unfenced.imports.length, 0);
  const lost = Object.assign(new Error('Tally write outcome is unknown.'), {tallyAmbiguous: true});
  const io = harness([[], []], {reply: lost});
  assert.equal((await saveVoucher(payment, io.options)).hold, 'uncertain_import');
  assert.equal(io.imports.length, 1);
  assert.equal(io.reads, 2);
  const {beforeImport, ...withoutFence} = harness([[]]).options;
  await assert.rejects(saveVoucher(payment, withoutFence), /durable voucher fence/);
});

test('retry-after-read: an acknowledged loss is reconciled once and a rejection is explained', async () => {
  const saved = harness([[], [observed(purchase)]], {reply: Object.assign(new Error('timeout'), {tallyAmbiguous: true})});
  assert.equal((await saveVoucher(purchase, saved.options)).outcome, 'saved');
  const rejected = Object.assign(new Error('Tally rejected the request.'), {tallyAmbiguous: true, tallyLineError: 'Voucher date is outside the financial year'});
  const io = harness([[], []], {reply: rejected});
  const result = await saveVoucher(purchase, io.options);
  assert.equal(result.hold, 'rejected');
  assert.match(result.message, /voucher date/);
  assert.equal(io.imports.length, 1);
});

test('changed masters, voucher types or cost centres hold before any voucher is read', async () => {
  const changed = [
    snapshot({ledgerRecords: ledgers.map(NAME => ({NAME, GUID: `${NAME}-guid`, PARENT: 'Group', ALTERID: NAME === 'Round Off' ? '13' : '12'}))}),
    snapshot({ledgerRecords: ledgers.map(NAME => ({NAME, GUID: `${NAME}-guid`, PARENT: NAME === 'Input CGST' ? 'Other' : 'Group', ALTERID: '12'}))}),
    snapshot({typeRecords: types.map(t => t.NAME === 'Purchase GST' ? {...t, ISACTIVE: 'No'} : t)}),
    snapshot({typeRecords: types.map(t => t.NAME === 'Purchase GST' ? {...t, PARENT: 'Journal'} : t)}),
    snapshot({typeRecords: types.map(t => t.NAME === 'Purchase GST' ? {...t, GUID: 'replaced'} : t)}),
    snapshot({centres: [{NAME: 'Site 4', GUID: 'other'}]}),
  ];
  for (const refs of changed) {
    const io = harness([[]], {references: refs});
    assert.equal((await saveVoucher(purchase, io.options)).hold, 'destination_changed');
    assert.equal(io.reads + io.imports.length, 0);
  }
});

test('a readback that differs from the approved voucher is never accepted', async () => {
  const off = observed(payment, {entries: [{ledger: 'Bank Charges', amount_cents: -1700}, {ledger: 'HDFC', amount_cents: 1700}]});
  assert.equal((await saveVoucher(payment, harness([[], [off]]).options)).hold, 'uncertain_import');
  const wrongType = observed(purchase, {voucher_type: 'Purchase'});
  assert.equal((await saveVoucher(purchase, harness([[], [wrongType]]).options)).hold, 'uncertain_import');
});

test('an unavailable Tally session becomes a hold with its state', async () => {
  const io = harness([[]]);
  io.options.requireCompany = async () => { throw new TallyUnavailable('company_not_open', 'Open Test in Tally.'); };
  const result = await saveVoucher(purchase, io.options);
  assert.deepEqual([result.outcome, result.hold, result.message], ['attention', 'company_not_open', 'Open Test in Tally.']);
});

test('voucher families follow reserved names through custom parents, keeping inactive types', () => {
  const {family, active} = voucherFamilies([...types, {NAME: 'Site Purchase', PARENT: 'Purchase GST', ISACTIVE: 'No'}, {NAME: 'Sales', '@_RESERVEDNAME': 'Sales'}]);
  assert.equal(family.get('site purchase'), 'purchase');
  assert.equal(family.get('debit note'), 'debit_note');
  assert.equal(family.get('contra'), 'contra');
  assert.equal(family.has('sales'), false);
  assert.equal(active.has('site purchase'), false);
  assert.equal(active.has('purchase gst'), true);
});

test("Tally's rejection reasons map to one short action each", () => {
  const cases = {
    "Voucher date is out of the financial year": "date",
    "Date is before Books beginning date": "date",
    "You are not authorised to create Vouchers": "permission",
    "Access denied for this user": "permission",
    "Voucher Type 'Purchase GST' does not exist": "voucher_type",
    "Voucher Number is required": "voucher_number",
    "Ledger 'Supplier' does not exist!": "ledger",
    "Something unusual": "other",
  };
  for (const [reason, code] of Object.entries(cases)) {
    const rejection = classifyRejection(reason);
    assert.equal(rejection.code, code, reason);
    assert.ok(rejection.message.length <= 300);
    assert.doesNotMatch(rejection.message, new RegExp(reason.slice(0, 12)), "native text stays in diagnostics");
  }
});
