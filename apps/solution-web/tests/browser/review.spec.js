/* global Buffer, URL, document, window */
import {test, expect} from '@playwright/test';

const workflow = {id:'w-1', key:'bill-entry', name:'Bill entry', description:'Enter purchase bills in Tally.',
  status:'active', employee_ids:[], config_schema:{properties:{}}, config_version:1,
  // The tenant's default locks one company; the launch starts on it, and the person may change it.
  config_values:{review_mode:'only_exceptions', company_mode:'locked', locked_company_guid:'g-test'},
  presentation:'desk-review', run_defaults:{company_mode:'infer'},
  run_schema:{properties:{review_mode:{enum:['all_outputs', 'only_exceptions']}, company_mode:{enum:['locked', 'infer']},
    locked_company_guid:{type:['string', 'null']}}}};
// A real title: one long file name, which must wrap rather than push the status off a phone's screen.
const task = {id:'t-1', workflow_id:'w-1', title:'Bill entry: 09-conflicting_version_of_the_supplier_invoice.pdf and 14 more',
  status:'attention', control_state:'active', progress:70,
  summary:'1 ready to save; 1 needs attention.', stage:'review', created_at:'2026-10-22T09:00:00Z',
  updated_at:'2026-10-22T09:05:00Z'};
const bill = {id:'b-1', version:2, kind:'bill', status:'proposed', file:'sunrise.pdf', bill:1,
  supplier:'Sunrise Office Systems', number:'SOS/26/0412', date:'2026-09-01', total:188800, company:'Test Company',
  voucher_type:'Purchase', review:['This supplier\'s bills have not been booked this way before. Review the voucher type and ledgers before approving.'],
  actions:[{action:'approve', label:'Approve'}, {action:'nothing', label:'Do nothing'}]};
const row = {id:'s-1', version:4, kind:'statement_row', status:'held', date:'2026-06-02', amount:'-2000.00',
  narration:'NEFT/QA18 BILLWISE STEEL/ON ACCOUNT', bank_ledger:'QA18 Bank Current', counter_ledger:'QA18 Billwise Steel',
  holds:[{code:'bill_unresolved', label:'Settlement unclear', reason:'Which of the party\'s open invoices this entry settles needs a person\'s choice.'}],
  review:['No set of open bills adds up to this amount, and the narration names none of them.'],
  actions:[{action:'settle', label:'On account, settling no bill', detail:{choice:0}},
    {action:'settle', label:'Settle 2,000.00 of QA18/OB/001 (5,000.00 open)', detail:{choice:1}},
    {action:'nothing', label:'Do nothing'}, {action:'retry', label:'Recheck'}]};
const saved = {id:'b-2', version:5, kind:'bill', status:'saved', file:'depot.pdf', bill:1, supplier:'QA18 Inventory Depot',
  number:'QA18/INV/STK/001', date:'2026-06-02', total:28202, company:'Test Company'};

async function console_(context, admin = true) {
  const calls = [];
  let records = [bill, row, saved];
  const counts = () => records.reduce((all, record) => ({...all, [record.status]:(all[record.status] ?? 0) + 1}), {});
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method();
    const base = '/api/tenants/mock-tenant/clients/rehearsal';
    let body;
    if (path === '/api/auth/session') body = {id:'user', name:'QA', memberships:[{slug:'mock-tenant', role:admin ? 'admin' : 'member'}], csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant', name:'QA'}, can_edit:admin,
      clients:[{id:'c-1', slug:'rehearsal', name:'Rehearsal companies'}], employees:[], workflows:[workflow], tasks:[task]};
    else if (path === '/api/tenants/mock-tenant/tasks/t-1') body = {...task, can_control:true,
      events:[{id:1, event_type:'review', summary:'Ready for review.', progress:70, created_at:'2026-10-22T09:05:00Z'}],
      run:{id:'r-1', client:'rehearsal'}};
    else if (path === `${base}/runs/r-1/status`) body = {run:{id:'r-1', task_id:'t-1', workflow_key:'bill-entry', state:'review',
      control_state:'active'}, items:{done:3}, records:counts(), blockers:[], activity:JSON.stringify(counts())};
    else if (path === `${base}/runs/r-1/records`) body = {records, next:null};
    else if (path === `${base}/records/b-1`) body = {...bill, facts:{}, preview:{party:'Sunrise Office Systems', voucher_type:'Purchase',
      lines:[{ledger:'Sunrise Office Systems', side:'credit', amount:188800}, {ledger:'Office Cabins', side:'debit', amount:160000},
        {ledger:'Input CGST 9%', side:'debit', amount:14400}, {ledger:'Input SGST 9%', side:'debit', amount:14400}]},
      evidence:[{field:'total', page:1, quote:'Invoice total 188,800.00'}], current:null};
    else if (path.startsWith(`${base}/records/`) && method === 'POST') {
      const id = path.split('/').at(-2), decision = request.postDataJSON();
      calls.push([id, decision]);
      records = records.map(record => record.id === id ? {...record, version:record.version + 1, status:'writing', holds:undefined,
        review:undefined, actions:[]} : record);
      body = {status:'writing', record_id:id, decided_version:decision.version, action:decision.action, replayed:false};
    } else if (path === `${base}/runs/r-1/approve`) {
      calls.push(['ready']);
      records = records.map(record => record.status === 'proposed' ? {...record, status:'writing', actions:[]} : record);
      body = {approved:1};
    } else if (path === `${base}/companies`) body = [{id:'co-1', name:'Test Company', guid:'g-test', books_from:'2026-04-01'},
      {id:'co-2', name:'Test Company', guid:'g-test', books_from:'2027-04-01'}];
    else if (path === '/api/tenants/mock-tenant/accounts/sources') {
      calls.push(['upload', request.postData().includes('name="paths"')]);
      body = {id:'src-1', files:[{id:'f-1', path:'sunrise.pdf'}]};
    } else if (path === `${base}/runs` && method === 'POST') {
      calls.push(['launch', request.postDataJSON()]);
      body = {run:{id:'r-1', task_id:'t-1', workflow_key:'bill-entry', state:'preparing', control_state:'active'},
        items:{}, records:{}, blockers:[], activity:null};
    } else throw Error(`${method} ${path}`);
    await route.fulfill({json:body});
  });
  // The PC finishes every save it was given; not enumerable, so `calls` still compares as the calls made.
  Object.defineProperty(calls, 'finish', {value:() => {
    records = records.map(record => record.status === 'writing' ? {...record, status:'saved'} : record);
  }});
  return calls;
}

test('a run is reviewed record by record, with the decisions each one allows', async ({page, context}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const calls = await console_(context);
  await page.goto('http://127.0.0.1:3000/mock-tenant/tasks/t-1');
  const review = page.getByRole('region', {name:'Review'});
  await expect(review).toContainText('1 needs a decision · 1 ready to approve · 1 saved in Tally');
  const proposed = review.getByRole('listitem').filter({hasText:'Sunrise Office Systems'});
  await expect(proposed).toContainText('No. SOS/26/0412 · 2026-09-01 · Test Company · Purchase');
  await expect(proposed).toContainText('1,88,800.00');
  await expect(proposed).toContainText('have not been booked this way before');
  await proposed.getByRole('button', {name:'Details'}).click();
  await expect(proposed.getByRole('table')).toContainText('Office Cabins');
  await expect(proposed).toContainText('total: “Invoice total 188,800.00” (page 1)');
  const held = review.getByRole('listitem').filter({hasText:'NEFT/QA18 BILLWISE STEEL'});
  await expect(held).toContainText('Settlement unclear');
  await expect(held).toContainText('paid to QA18 Billwise Steel · QA18 Bank Current');
  for (const theme of ['minkops-light', 'minkops-dark', 'slate-light', 'slate-dark']) {
    await page.getByRole('combobox', {name:'Theme', exact:true}).selectOption(theme);
    await page.screenshot({path:testInfo.outputPath(`review-${theme}.png`), fullPage:true});
    await held.screenshot({path:testInfo.outputPath(`review-held-${theme}.png`)});
  }
  await held.getByRole('button', {name:'Settle 2,000.00 of QA18/OB/001 (5,000.00 open)'}).click();
  await expect(page.getByRole('status').filter({hasText:'Approved. Saving it in Tally.'})).toBeVisible();
  await expect(held).toContainText('Saving');
  await review.getByRole('button', {name:'Save ready entries'}).click();
  await expect(page.getByRole('status').filter({hasText:'1 entry approved. Saving in Tally.'})).toBeVisible();
  await expect(proposed).toContainText('Saving');
  expect(calls).toEqual([['s-1', {action:'settle', version:4, detail:{choice:1}}], ['ready']]);
  // Once nothing is saving, a notice that something is saving goes; the counts say how it ended.
  calls.finish();
  await expect(review).toContainText('3 saved in Tally');
  await expect(page.getByRole('status').filter({hasText:'Saving'})).toHaveCount(0);
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('a run starts from its workflow with the client, the files and the settings it declares', async ({page, context}) => {
  const calls = await console_(context);
  await page.goto('http://127.0.0.1:3000/mock-tenant/workflows/w-1');
  const form = page.locator('form').filter({hasText:'Start a run'});
  await expect(form.getByRole('combobox', {name:'Client'})).toHaveValue('rehearsal');
  // A company split by year is offered once: each bill goes to the part whose books cover its date.
  await expect(form.getByRole('combobox', {name:'Company'}).locator('option')).toHaveText([
    'The company each bill is addressed to', 'Test Company']);
  await expect(form.getByRole('combobox', {name:'Company'})).toHaveValue('g-test');
  await form.getByLabel('Files').setInputFiles({name:'sunrise.pdf', mimeType:'application/pdf', buffer:Buffer.from('%PDF-1.4')});
  // The option says each bill goes where it is addressed, so the run asks for exactly that, whatever the default.
  await form.getByRole('combobox', {name:'Company'}).selectOption({label:'The company each bill is addressed to'});
  await form.getByRole('button', {name:'Start run'}).click();
  await expect(page).toHaveURL(/\/mock-tenant\/tasks\/t-1$/);
  const [upload, [, launch]] = calls;
  expect(upload).toEqual(['upload', true]);
  expect(launch).toEqual({workflow:'bill-entry', file_ids:['f-1'], config:{company_mode:'infer'},
    request_key:expect.stringMatching(/^[0-9a-f-]{36}$/)});
});

test('a held bill is approved with the ledgers a person chooses, from those its session weighed first', async ({page, context}) => {
  const errors = [], calls = [];
  page.on('pageerror', error => errors.push(error.message));
  const base = '/api/tenants/mock-tenant/clients/rehearsal';
  let held = {id:'b-9', version:3, kind:'bill', status:'held', file:'cabin.pdf', bill:1, supplier:'Sunrise Office Systems',
    number:'SOS/26/0412', date:'2026-09-01', total:188800, company:'Test Company',
    holds:[{code:'classification_uncertain', label:'Ledger unclear', reason:'The appropriate accounting ledger could not be confirmed.'}],
    review:['Office Cabins or Repairs and Maintenance?'],
    actions:[{action:'choose', label:'Choose and approve'}, {action:'nothing', label:'Do nothing'}, {action:'retry', label:'Recheck'}]};
  const choice = {company:'Test Company', supplier:'Sunrise Office Systems',
    voucher_types:[{guid:'g-journal', name:'Journal'}, {guid:'g-purchase', name:'Purchase'}], voucher_type:'g-purchase',
    party:{guid:'g-sunrise', name:'Sunrise Office Systems'},
    lines:[{role:'expense', side:'debit', amount:160000, ledger:{guid:'g-cabins', name:'Office Cabins'}, picker:'expense'},
      {role:'tax', side:'debit', amount:14400, ledger:{guid:'g-cgst', name:'Input CGST 9%'}, picker:'tax'},
      {role:'tax', side:'debit', amount:14400, ledger:{guid:'g-sgst', name:'Input SGST 9%'}, picker:'tax'}],
    items:[], candidates:[{guid:'g-cabins', name:'Office Cabins'}, {guid:'g-repairs', name:'Repairs and Maintenance'}]};
  const ledgers = {
    expense:[{guid:'g-cabins', name:'Office Cabins', group:'Fixed Assets', suggested:true},
      {guid:'g-repairs', name:'Repairs and Maintenance', group:'Indirect Expenses', suggested:true},
      {guid:'g-round', name:'Round Off', group:'Indirect Expenses'}],
    tax:[{guid:'g-cgst', name:'Input CGST 9%', group:'Duties & Taxes'}, {guid:'g-sgst', name:'Input SGST 9%', group:'Duties & Taxes'}],
    supplier:[{guid:'g-sunrise', name:'Sunrise Office Systems', group:'Sundry Creditors'}]};
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method();
    let body, status = 200;
    if (path === '/api/auth/session') body = {id:'user', name:'QA', memberships:[{slug:'mock-tenant', role:'admin'}], csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant', name:'QA'}, can_edit:true,
      clients:[{id:'c-1', slug:'rehearsal', name:'Rehearsal companies'}], employees:[], workflows:[workflow], tasks:[task]};
    else if (path === '/api/tenants/mock-tenant/tasks/t-1') body = {...task, can_control:true, events:[], run:{id:'r-1', client:'rehearsal'}};
    else if (path === `${base}/runs/r-1/status`) body = {run:{id:'r-1', task_id:'t-1', workflow_key:'bill-entry', state:'review',
      control_state:'active'}, items:{done:1}, records:{[held.status]:1}, blockers:[], activity:held.status};
    else if (path === `${base}/runs/r-1/records`) body = {records:[held], next:null};
    else if (path === `${base}/records/b-9`) body = {...held, facts:{}, choice};
    else if (path === `${base}/records/b-9/ledgers`) {
      const role = url.searchParams.get('role'), query = (url.searchParams.get('q') ?? '').toLowerCase();
      calls.push(['ledgers', role, query]);
      body = {company:'Test Company', role, ledgers:ledgers[role].filter(ledger => ledger.name.toLowerCase().includes(query))};
    } else if (path === `${base}/records/b-9/decisions` && method === 'POST') {
      const decision = request.postDataJSON();
      calls.push(['decide', decision]);
      if (decision.detail.lines[0] === 'g-round') {
        status = 422;
        body = {detail:'Round Off is not where this bill goes. Choose again.'};
      } else {
        held = {...held, version:4, status:'writing', holds:undefined, review:undefined, actions:[]};
        body = {status:'writing', record_id:'b-9', decided_version:3, action:'choose', replayed:false};
      }
    } else throw Error(`${method} ${path}`);
    await route.fulfill({status, json:body});
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/tasks/t-1');
  const row = page.getByRole('region', {name:'Review'}).getByRole('listitem').filter({hasText:'Sunrise Office Systems'});
  await row.getByRole('button', {name:'Choose and approve'}).click();
  const form = row.getByRole('form', {name:'Choose and approve'});
  await expect(form).toContainText('Minkops weighed Office Cabins and Repairs and Maintenance; they are listed first.');
  await expect(form.getByLabel('Voucher type')).toHaveValue('g-purchase');
  const expense = form.getByRole('combobox', {name:'Expense 1,60,000.00 Dr'});
  await expect(expense).toHaveValue('g-cabins');
  await expect(expense.locator('option')).toHaveText(['Choose a ledger', 'Office Cabins · Fixed Assets · suggested',
    'Repairs and Maintenance · Indirect Expenses · suggested', 'Round Off · Indirect Expenses']);
  // A search narrows the ledgers offered; the server refuses a choice its checks reject, and says why.
  await form.getByRole('searchbox', {name:'Search ledgers for Expense 1,60,000.00 Dr'}).fill('round');
  await expect(expense.locator('option')).toHaveText(['Choose a ledger', 'Office Cabins', 'Round Off · Indirect Expenses']);
  await expense.selectOption('g-round');
  await form.getByRole('button', {name:'Approve with these ledgers'}).click();
  await expect(page.getByRole('status').filter({hasText:'Round Off is not where this bill goes.'})).toBeVisible();
  await form.getByRole('searchbox', {name:'Search ledgers for Expense 1,60,000.00 Dr'}).fill('');
  await expense.selectOption('g-repairs');
  await form.getByRole('button', {name:'Approve with these ledgers'}).click();
  await expect(page.getByRole('status').filter({hasText:'Approved. Saving it in Tally.'})).toBeVisible();
  await expect(row).toContainText('Saving');
  const decisions = calls.filter(([kind]) => kind === 'decide').map(([, decision]) => decision);
  expect(decisions).toEqual([
    {action:'choose', version:3, detail:{voucher_type:'g-purchase', party:'g-sunrise', lines:['g-round', 'g-cgst', 'g-sgst']}},
    {action:'choose', version:3, detail:{voucher_type:'g-purchase', party:'g-sunrise', lines:['g-repairs', 'g-cgst', 'g-sgst']}}]);
  expect(calls).toContainEqual(['ledgers', 'supplier', '']);
  expect(errors).toEqual([]);
});

test('a missing supplier is created as Tally would hold it, then its bill is entered as the person chose', async ({page, context}) => {
  const errors = [], decisions = [];
  page.on('pageerror', error => errors.push(error.message));
  const base = '/api/tenants/mock-tenant/clients/rehearsal';
  let held = {id:'b-7', version:2, kind:'bill', status:'held', file:'cabins.pdf', bill:1, supplier:'Cabin Services UAT',
    number:'CS/26/0001', date:'2026-09-02', total:8850, company:'Test Company',
    holds:[{code:'supplier_missing', label:'Missing supplier', reason:'The supplier is missing from the company\'s confirmed Tally ledgers.'}],
    actions:[{action:'supplier', label:'Create this ledger'}, {action:'choose', label:'Choose and approve'},
      {action:'nothing', label:'Do nothing'}, {action:'retry', label:'Recheck'}]};
  const detail = {...held, facts:{}, choice:{company:'Test Company', supplier:'Cabin Services UAT',
    voucher_types:[{guid:'g-purchase', name:'Purchase'}], voucher_type:'g-purchase', party:null,
    lines:[{role:'expense', side:'debit', amount:7500, ledger:{guid:'g-repairs', name:'Repairs and Maintenance'}, picker:'expense'},
      {role:'tax', side:'debit', amount:675, ledger:{guid:'g-cgst', name:'Input CGST 9%'}, picker:'tax'},
      {role:'tax', side:'debit', amount:675, ledger:{guid:'g-sgst', name:'Input SGST 9%'}, picker:'tax'}], items:[], candidates:[]},
    new_ledger:{form:{name:'Cabin Services UAT', under:'Sundry Creditors', groups:['Sundry Creditors', 'Creditors - Steel'],
      billwise:null, credit_period:null, mailing:{address:['Plot 12, Auto Nagar'], state:'Andhra Pradesh', country:'India',
        pincode:'522001'}, gst:{registration_type:'Regular', gstin:'37CABFC2610A1Z5'}},
      printed:{name:'Cabin Services UAT', gstin:'37CABFC2610A1Z5'}}};
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method();
    let body;
    if (path === '/api/auth/session') body = {id:'user', name:'QA', memberships:[{slug:'mock-tenant', role:'admin'}], csrf_token:'csrf'};
    else if (path.endsWith('/workspace')) body = {tenant:{slug:'mock-tenant', name:'QA'}, can_edit:true,
      clients:[{id:'c-1', slug:'rehearsal', name:'Rehearsal companies'}], employees:[], workflows:[workflow], tasks:[task]};
    else if (path === '/api/tenants/mock-tenant/tasks/t-1') body = {...task, can_control:true, events:[], run:{id:'r-1', client:'rehearsal'}};
    else if (path === `${base}/runs/r-1/status`) body = {run:{id:'r-1', task_id:'t-1', workflow_key:'bill-entry', state:'review',
      control_state:'active'}, items:{done:1}, records:{[held.status]:1}, blockers:[], activity:held.status};
    else if (path === `${base}/runs/r-1/records`) body = {records:[held], next:null};
    else if (path === `${base}/records/b-7`) body = detail;
    else if (path === `${base}/records/b-7/ledgers`) body = {ledgers:[]};
    else if (path === `${base}/records/b-7/decisions` && method === 'POST') {
      decisions.push(request.postDataJSON());
      held = {...held, version:3, status:'writing', holds:undefined, actions:[]};
      body = {status:'writing', record_id:'b-7', decided_version:2, action:'supplier', replayed:false};
    } else throw Error(`${method} ${path}`);
    await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/tasks/t-1');
  const row = page.getByRole('region', {name:'Review'}).getByRole('listitem').filter({hasText:'Cabin Services UAT'});
  await row.getByRole('button', {name:'Create this ledger'}).click();
  const form = row.getByRole('form', {name:'Create this ledger'});
  await expect(form).toContainText('The bill prints name: Cabin Services UAT · gstin: 37CABFC2610A1Z5.');
  await expect(form.getByLabel('Name')).toHaveValue('Cabin Services UAT');
  await expect(form.getByLabel('Under')).toHaveValue('Sundry Creditors');
  // No supplier of the company's says how balances are kept yet: nothing is created until the person chooses.
  const create = form.getByRole('button', {name:'Create ledger and approve'});
  await expect(create).toBeDisabled();
  await form.getByLabel('Maintain balances bill-by-bill').selectOption('yes');
  await form.getByLabel('Default credit period (days)').fill('30');
  await create.click();
  await expect(page.getByRole('status').filter({hasText:'Approved. Saving it in Tally.'})).toBeVisible();
  expect(decisions).toEqual([{action:'supplier', version:2, detail:{
    ledger:{name:'Cabin Services UAT', under:'Sundry Creditors', billwise:true, credit_period:30,
      mailing:{address:['Plot 12, Auto Nagar'], state:'Andhra Pradesh', country:'India', pincode:'522001'},
      gst:{registration_type:'Regular', gstin:'37CABFC2610A1Z5'}},
    voucher_type:'g-purchase', lines:['g-repairs', 'g-cgst', 'g-sgst']}}]);
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
