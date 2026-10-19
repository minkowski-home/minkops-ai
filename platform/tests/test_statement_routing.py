import copy
import pytest
from minkops_platform.accounts.statement_routing import route


def context():
    def master(kind, name, **fields):
        return {'type':kind,'data':{'NAME':name,'GUID':name+'-guid','ALTERID':'1',**fields}}
    return [{'company':'Test','company_guid':'company','port':9000,'identity':{'BOOKSFROM':'20260401'},'masters':{'records':[
        master('LEDGER','Bank',PARENT='Bank Accounts'), master('LEDGER','Expense',PARENT='Indirect Expenses'),
        master('VOUCHERTYPE','Payment',PARENT='Payment'), master('VOUCHERTYPE','Receipt',PARENT='Receipt')]}}]


def test_branch_kind_drives_company_or_ledger_with_exact_normalized_unique_matching():
    companies=context()
    config={'other_side_ledger':'Expense','bank_ledgers':{'company':'Bank'}}
    row={'branch':'  tEsT  ','date':'2026-10-01','amount_cents':-100}
    result=route(row,companies,config)
    assert result['company_guid']=='company' and result['data']['counter_ledger']=='Expense'
    row['branch']=' eXpense '
    assert route(row,companies,config)['matched_kind']=='LEDGER'
    other=copy.deepcopy(companies[0]); other.update(company='Other',company_guid='other')
    with pytest.raises(ValueError,match='exactly one'): route(row,[*companies,other],config)


def test_bank_counter_and_books_date_are_discovery_validated():
    companies=context(); row={'branch':'Test','date':'2026-10-01','amount_cents':100}
    for config in ({'other_side_ledger':'Missing','bank_ledgers':{'company':'Bank'}},
                   {'other_side_ledger':'Expense','bank_ledgers':{'company':'Expense'}}):
        with pytest.raises(ValueError): route(row,companies,config)
    row['date']='2026-03-31'
    with pytest.raises(ValueError,match='books'):route(row,companies,{'other_side_ledger':'Expense','bank_ledgers':{'company':'Bank'}})


def test_group_and_cost_category_routing_refuse_ambiguous_posting_destinations():
    companies=context(); records=companies[0]['masters']['records']
    config={'other_side_ledger':'Expense','bank_ledgers':{'company':'Bank'}}
    row={'branch':'Indirect Expenses','date':'2026-10-01','amount_cents':-100}
    records.append({'type':'GROUP','data':{'NAME':'Indirect Expenses','GUID':'group'}})
    assert route(row,companies,config)['data']['counter_ledger']=='Expense'
    records.extend([{'type':'COSTCATEGORY','data':{'NAME':'Projects','GUID':'category'}},
        {'type':'COSTCENTRE','data':{'NAME':'Site One','GUID':'centre','CATEGORY':'Projects'}}])
    row['branch']='Site One'
    with pytest.raises(ValueError,match='enable cost centres'):route(row,companies,config)
    records[1]['data']['ISCOSTCENTRESON']='Yes'
    assert route(row,companies,config)['allocation']['centre']=='Site One'
    row['branch']='Projects'
    assert route(row,companies,config)['allocation']['category']=='Projects'
    records.append({'type':'COSTCENTRE','data':{'NAME':'Site Two','GUID':'centre-two','CATEGORY':'Projects'}})
    with pytest.raises(ValueError,match='exactly one cost centre'):route(row,companies,config)

