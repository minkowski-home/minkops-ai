"""Opt-in missing-supplier decision proof using the paid scan and native adapter.

Uses verify_discovery_context_live's isolated DB, credentials and checkpoint.
Requires a previously confirmed discovery and preserves every paid run ID.
"""
import json
import uuid
import psycopg
import pymupdf
from minkops_platform.installation import install, load_solution
import verify_discovery_context_live as proof


def attention_job(create=False):
    job = proof.api('post', '/api/desktop/worker/claim', headers=proof.worker, json={})
    assert job and job['operation'] == ('attention.supplier' if create else 'attention.refresh'), job
    route = f"/api/desktop/worker/jobs/{job['id']}"
    plan = proof.api('get', route + '/plan?claim_token=' + job['claim_token'], headers=proof.worker)
    try:
        observed = proof.native({'operation': 'attention', 'plan': plan, 'create_supplier': create})
    except Exception as error:
        proof.api('post', route + '/finish', headers=proof.worker,
                  json={'claim_token': job['claim_token'], 'error': str(error)[-300:]})
        raise
    receipt = {'claim_token': job['claim_token'], 'result': observed}
    proof.api('post', route + '/finish', headers=proof.worker, json=receipt)
    proof.api('post', route + '/finish', headers=proof.worker, json=receipt)
    return observed


def main():
    proof.connect()
    state = proof.state
    assert state.get('discovery_id') and state.get('catalog'), 'Confirm discovery first.'
    with psycopg.connect(proof.DATABASE) as connection:
        install(connection, load_solution(proof.ROOT, 'mock-client'), actor_email='demo@example.com')
    if 'supplier_run_id' not in state:
        company = state['catalog']['sources'][0]['snapshot']['companies'][0]
        state['new_supplier'] = 'MIN124 New Supplier ' + uuid.uuid4().hex[:8]
        state['supplier_invoice'] = 'MIN124-NEW-' + uuid.uuid4().hex[:8]
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((60, 80), '\n'.join([
            'SYNTHETIC TEST INVOICE - NOT A VALID TAX DOCUMENT',
            'Supplier: ' + state['new_supplier'], 'Invoice Number: ' + state['supplier_invoice'],
            'Invoice Date: 01 October 2026', 'Bill to / Buyer legal name: ' + company['company'],
            'Description: Materials expense, accounting voucher without inventory/cost allocations',
            'Purchase expense allocation: MIN124 Purchases',
            'Subtotal: INR 117.00', 'Tax: INR 0.00 (non GST test transaction)', 'Total payable: INR 117.00',
        ]), fontsize=11)
        source = proof.api('post', proof.base + '/accounts/sources', headers=proof.csrf,
            data={'paths': '["new-supplier.pdf"]'}, files=[('files', ('new-supplier.pdf', doc.tobytes()))])
        doc.close()
        state['supplier_file_id'] = source['files'][0]['id']
        run = proof.api('post', proof.base + '/accounts/runs', headers=proof.csrf, json={
            'key': 'bill-entry', 'request_key': str(uuid.uuid4()), 'file_ids': [state['supplier_file_id']],
            'config': {'output_mode': 'tally_in_place', 'discovery_id': state['discovery_id'], 'company_mode': 'infer'}})
        state['supplier_run_id'] = run['id']
        proof.checkpoint()
    path = proof.base + '/accounts/runs/' + state['supplier_run_id']
    proof.hosted(state['supplier_run_id'])
    run = proof.api('get', path)
    if run['state'] == 'review' and not run['tally_writes']:
        assert len(run['result']['records']) == 1, run['result']
        record = run['result']['records'][0]
        assert record['data']['vendor'] == state['new_supplier'], record
        assert record['data']['total'] == 117 and record['data']['tax'] == 0, record
        assert run['result']['unresolved'], run['result']
        (proof.DATA / 'supplier-review.json').write_text(json.dumps(run, default=str, indent=2))
        if not state.get('supplier_authorized'):
            proof.api('post', proof.base + f"/attention/bills/{run['id']}/{state['supplier_file_id']}",
                      headers=proof.csrf, json={'action': 'supplier'})
            state['supplier_authorized'] = True
            proof.checkpoint()
        attention_job(create=True)
        run = proof.api('get', path)
    while run['state'] == 'writing':
        proof.finish_job('save')
        run = proof.api('get', path)
    assert run['state'] == 'completed' and all(w['verified_at'] for w in run['tally_writes']), run
    items = proof.api('get', proof.base + '/attention?status=all')
    for item in items:
        if item['task_id'] == run['task_id'] and item['status'] == 'pending':
            proof.api('post', proof.base + f"/attention/{item['id']}/refresh", headers=proof.csrf)
            attention_job()
    items = proof.api('get', proof.base + '/attention?status=all')
    assert any(i['task_id'] == run['task_id'] and i['status'] == 'done' for i in items), items
    (proof.DATA / 'supplier-receipts.json').write_text(json.dumps(run, default=str, indent=2))
    print('Paid new-supplier scan, explicit native master creation, same-bill continuation and verified save passed.', flush=True)


if __name__ == '__main__':
    main()
