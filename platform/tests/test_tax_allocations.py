"""Split tax preserves distinct native identities and exact source amounts."""
import copy
import pytest
from test_master_selection import target, record
from minkops_platform.accounts.master_selection import resolve_masters
from minkops_platform.accounts.bills import validate_tally, allocation_entries

def split():
    t = target(extra=[{'NAME':'Input CGST','GUID':'cgst','PARENT':'Duties & Taxes'},
                      {'NAME':'Input SGST','GUID':'sgst','PARENT':'Duties & Taxes'}])
    r = record(t)
    refs = {v['name']:k for k,v in t['ledger_refs'].items()}
    r['data'].update(subtotal=100,tax=18,total=118,cost_code=None)
    r['tax_allocations'] = [{'ref':refs[name],'amount':9,'evidence':name+' 9.00 printed on page 1'}
                            for name in ('Input CGST','Input SGST')]
    return t,r

def test_split_tax_resolves_both_master_ids_and_balances_without_combining():
    t,r=split()
    resolve_masters(r,t,required=True,allow_split=True)
    validate_tally(r['data'],t,r['tax_allocations'])
    assert r['data']['tax_ledger'] is None
    assert allocation_entries(r['data'],r['tax_allocations']) == [
        {'ledger':'Input CGST','amount':9},{'ledger':'Input SGST','amount':9}]

@pytest.mark.parametrize('change',[
    lambda r:r['tax_allocations'][0].update(amount=-9),
    lambda r:r['tax_allocations'][0].update(amount=9.001),
    lambda r:r['tax_allocations'][0].update(amount=8),
    lambda r:r['tax_allocations'][0].update(amount=True),
    lambda r:r['tax_allocations'][0].update(ref='foreign'),
    lambda r:r['tax_allocations'][1].update(ref=r['tax_allocations'][0]['ref']),
    lambda r:r['data'].update(tax_ledger='Input CGST'),
    lambda r:r['data'].update(tax=0,total=100),
])
def test_invalid_split_is_held_atomically(change):
    t,r=split();change(r);before=copy.deepcopy(r)
    with pytest.raises(ValueError):resolve_masters(r,t,required=True,allow_split=True)
    assert r==before

def test_legacy_contract_cannot_silently_accept_allocations():
    t,r=split()
    with pytest.raises(ValueError,match='split'):resolve_masters(r,t,required=True)
