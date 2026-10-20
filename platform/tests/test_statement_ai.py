"""Model classification cannot change source money or escape pinned discovery."""
import copy

import pytest

from minkops_platform.accounts.statement_routing import validated_plan
from minkops_platform.accounts.statements import StatementHandler
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import load_definition


def companies():
    def master(kind, name, **fields):
        return {'type':kind,'data':{'NAME':name,'GUID':name+'-guid','ALTERID':'1',**fields}}
    return [{'company':'Test','company_guid':'company','port':9000,'identity':{'BOOKSFROM':'20260401'},'masters':{'records':[
        master('LEDGER','Bank',PARENT='Bank Accounts'), master('LEDGER','Expense',PARENT='Indirect Expenses'),
        master('LEDGER','Rent',PARENT='Indirect Expenses'),
        master('VOUCHERTYPE','Payment',PARENT='Payment'), master('VOUCHERTYPE','Receipt',PARENT='Receipt'),
        master('LEDGER','ICICI',PARENT='Bank Accounts'), master('LEDGER','Input GST',PARENT='Duties & Taxes'),
        master('VOUCHERTYPE','Contra',PARENT='Contra')]}}]


def choice(**overrides):
    return {'source_file_id':'file','sheet':'','row':3,'company_guid':'company',
        'bank_ledger_guid':'Bank-guid','counter_ledger_guid':'Rent-guid','voucher_type_guid':'Payment-guid',
        'cost_centre_guid':None,'cost_category_guid':None,'evidence':'Office rent narration and comparable Payment allocation.',
        'exception':None,**overrides}


def row(**overrides):
    return {'source_file_id':'file','source_file':'statement.csv','sheet':'','row':3,'branch':'Client label 17',
        'narration':'October office rent','date':'2026-10-01','amount_cents':-10000,'balance_cents':90000,
        'identity':'stable-source-identity','status':'ready',**overrides}


def validate(rows, proposals):
    run={'tenant_id':'tenant','config':{'statement_context':{'sources':[{'tool':'tally','snapshot':{'companies':companies()}}]}}}
    return StatementHandler().validate(run,[],{}, {'rows':rows}, {'records':proposals})['records']


def test_unknown_branch_does_not_choose_or_block_the_model_selected_ledger():
    plan=validated_plan(row(),companies(),choice())
    assert plan['data']['counter_ledger']=='Rent'
    assert plan['data']['amount_cents']==-10000
    assert plan['references']['ledgers']['Rent']['GUID']=='Rent-guid'


@pytest.mark.parametrize('changes',[
    {'company_guid':'outside'}, {'bank_ledger_guid':'Expense-guid'},
    {'counter_ledger_guid':'made-up'}, {'counter_ledger_guid':'Bank-guid'},
    {'voucher_type_guid':'Receipt-guid'}, {'cost_centre_guid':'unknown'},
])
def test_invalid_model_destinations_never_become_native_writes(changes):
    with pytest.raises(ValueError):validated_plan(row(),companies(),choice(**changes))


def test_identity_is_company_scoped_and_duplicate_native_guids_hold():
    context=companies()
    other=copy.deepcopy(context[0])
    other.update(company='Other',company_guid='other')
    assert validated_plan(row(),[*context,other],choice())['company_guid']=='company'
    collision=copy.deepcopy(context[0]['masters']['records'][2])
    collision['data']['PARENT']='Different group'
    context[0]['masters']['records'].append(collision)
    with pytest.raises(ValueError):validated_plan(row(),context,choice())


def test_books_date_active_type_and_cost_relationships_are_native_constraints():
    with pytest.raises(ValueError,match='books'):
        validated_plan(row(date='2026-03-31'),companies(),choice())
    context=companies()
    records=context[0]['masters']['records']
    records[3]['data']['ISACTIVE']='No'
    with pytest.raises(ValueError,match='active'):validated_plan(row(),context,choice())
    context=companies()
    records=context[0]['masters']['records']
    records.extend([{'type':'COSTCATEGORY','data':{'NAME':'Projects','GUID':'category'}},
        {'type':'COSTCENTRE','data':{'NAME':'Site One','GUID':'centre','CATEGORY':'Projects'}}])
    selected=choice(cost_centre_guid='centre',cost_category_guid='category')
    with pytest.raises(ValueError,match='enable cost centres'):validated_plan(row(),context,selected)
    records[2]['data']['ISCOSTCENTRESON']='Yes'
    assert validated_plan(row(),context,selected)['allocation']['centre']=='Site One'
    records[-1]['data']['CATEGORY']='Different category'
    with pytest.raises(ValueError,match='does not belong'):validated_plan(row(),context,selected)


def test_omissions_uncertainty_and_invalid_selection_hold_only_their_rows():
    result=validate([row(),row(row=4),row(row=5),row(row=6)], [choice(),
        choice(row=4,exception={'code':'classification_uncertain','detail':'Two equally plausible ledgers.'}),
        choice(row=5,counter_ledger_guid='invented')])
    assert [r['status'] for r in result]==['ready','held','held','held']
    assert all('plan' not in r for r in result[1:])
    assert result[1]['code']=='classification_uncertain'


def test_source_balance_failure_and_money_cannot_be_overridden():
    held=row(code='statement_balance',reason='Balance mismatch.',status='held')
    assert validate([held],[choice()])[0]['code']=='statement_balance'
    result=validate([row()],[choice(amount_cents=-1,date='2026-01-01')])[0]
    assert result['amount_cents']==-10000 and result['plan']['data']['amount_cents']==-10000


def test_duplicate_and_unknown_model_row_references_are_rejected():
    for proposals in ([choice(),choice()], [choice(row=999)], [choice(source_file_id='other')]):
        with pytest.raises(ValueError):validate([row()],proposals)


def test_overlap_conflicts_hold_every_copy_and_identical_choices_share_intent():
    rows=[row(),row(source_file_id='overlap')]
    result=validate(rows,[choice(),choice(source_file_id='overlap',counter_ledger_guid='Expense-guid')])
    assert all(r['code']=='statement_conflict' for r in result)
    assert validate(rows,[choice(),choice(source_file_id='overlap')])[1]['duplicate_of']==0


def test_statement_uses_a_hosted_skill_without_legacy_routing_settings():
    definition=load_definition(REPOSITORY_ROOT/'employees/accounts-desk/workflows/statement-entry')
    assert definition.execution_snapshot['execution']['model']=='gpt-6-luna'
    assert not getattr(StatementHandler(),'deterministic',False)
    assert 'other_side_ledger' not in definition.tenant_schema['properties']
    assert 'bank_ledgers' not in definition.run_schema['properties']


def lines_of(plan):
    return [(line['ledger'], line['side'], line['amount_cents']) for line in plan['lines']]


def test_bank_charges_with_gst_split_into_native_lines_that_add_up_exactly():
    rows=[row(amount_cents=-1770,narration='NEFT charges incl GST')]
    split=[{'role':'charge','ledger_guid':'Expense-guid','amount':15.0,'cost_centre_guid':None,'cost_category_guid':None},
           {'role':'tax','ledger_guid':'Input GST-guid','amount':2.7,'cost_centre_guid':None,'cost_category_guid':None}]
    [record]=validate(rows,[choice(counter_ledger_guid='Expense-guid',lines=split)])
    plan=record['plan']
    assert (plan['format_version'],plan['family'],plan['duplicate']['strategy'])==(5,'payment','tag')
    assert lines_of(plan)==[('Bank','credit',1770),('Expense','debit',1500),('Input GST','debit',270)]
    assert record['counter_ledger']=='Expense + Input GST'
    off=[{**split[0],'amount':16.0},split[1]]
    [held]=validate([row(amount_cents=-1770)],[choice(counter_ledger_guid='Expense-guid',lines=off)])
    assert (held['status'],held['code'])==('held','statement_interpretation')


def contra(row_number, bank, other, pair):
    return choice(row=row_number,bank_ledger_guid=bank+'-guid',counter_ledger_guid=other+'-guid',voucher_type_guid='Contra-guid',
                  family='contra',pair={'source_file_id':'file','sheet':'','row':pair} if pair else None)


def test_both_legs_of_a_transfer_become_one_contra_written_by_the_paying_leg():
    rows=[row(row=3,amount_cents=-500000,identity='leg-out'),row(row=4,amount_cents=500000,date='2026-10-02',identity='leg-in')]
    out,into=validate(rows,[contra(3,'Bank','ICICI',4),contra(4,'ICICI','Bank',3)])
    assert lines_of(out['plan'])==[('Bank','credit',500000),('ICICI','debit',500000)]
    assert out['plan']['identity']['legs']==['leg-in','leg-out'] and out['plan']['destination_key']=='statement:company:contra'
    assert (into.get('plan'),into['duplicate_of'],into['covered_by_transfer'])==(None,0,True)


def test_mismatched_or_one_sided_transfers_never_write_two_vouchers():
    rows=[row(row=3,amount_cents=-500000,identity='leg-out'),row(row=4,amount_cents=400000,identity='leg-in')]
    out,into=validate(rows,[contra(3,'Bank','ICICI',4),contra(4,'ICICI','Bank',3)])
    assert {out['code'],into['code']}=={'statement_transfer_unpaired'}
    [lone]=validate([row(amount_cents=-500000)],[contra(3,'Bank','ICICI',None)])
    assert lone['plan']['duplicate']['strategy']=='counterpart'
    assert lone['plan']['duplicate']['window']=={'from':'2026-09-28','to':'2026-10-04'}
    [expense]=validate([row(amount_cents=-500000)],[contra(3,'Bank','Rent',None)])
    assert expense['code']=='statement_interpretation'
