"""Bind agent-selected native identities; never classify a transaction in Python."""
from decimal import Decimal

from minkops_connectors.statement import normalized

from .client_context import books_beginning, master_lookup
from .supplier_gst import scalar
from .voucher_types import base_types


def name(master):
    return scalar(master.get('@_NAME') or master.get('NAME'))


def one(values, message):
    if len(values) != 1: raise ValueError(message)
    return values[0]


def destination_choices(company):
    """Small launch metadata; never send full native masters to the renderer."""
    records=master_lookup(company)['records']
    groups={normalized(name(r['data'])):scalar(r['data'].get('PARENT')) for r in records if r['type']=='GROUP'}
    def bank(master):
        parent=scalar(master.get('PARENT'))
        for _ in range(50):
            if normalized(parent)=='bank accounts':return True
            parent=groups.get(normalized(parent))
            if not parent:return False
        return False
    types=[r['data'] for r in records if r['type']=='VOUCHERTYPE']
    bases=base_types(types)
    return {'banks':[{'name':name(r['data']),'guid':scalar(r['data'].get('GUID'))} for r in records if r['type']=='LEDGER' and bank(r['data'])],
        'voucher_types':[{'name':name(m),'guid':scalar(m.get('GUID')),'base':normalized(bases.get(name(m).casefold()))}
            for m in types if normalized(bases.get(name(m).casefold())) in ('payment','receipt') and scalar(m.get('ISACTIVE')).casefold()!='no']}


def validated_plan(row, companies, selection):
    """Financial facts come from the immutable source, identities from discovery.

    The skill chooses company, bank, counter ledger and optional cost allocation.
    These checks only constrain that proposal to the supported native contract.
    """
    company=one([c for c in companies if c['company_guid']==selection.get('company_guid')],
        'The interpretation must identify one discovered company.')
    records=master_lookup(company)['records']
    def selected(kind, field):
        guid=selection.get(field)
        return one([r['data'] for r in records if r['type']==kind and guid and scalar(r['data'].get('GUID'))==guid],
            f'The interpretation must select one discovered {kind.lower()} identity for {field}.')
    if not str(selection.get('evidence') or '').strip():
        raise ValueError('The ledger interpretation needs source and discovery evidence.')
    beginning=books_beginning(company['identity'])
    if beginning and row['date']<beginning: raise ValueError('The transaction date precedes the company books beginning date.')
    bank=selected('LEDGER','bank_ledger_guid')
    counter=selected('LEDGER','counter_ledger_guid')
    groups={normalized(name(r['data'])):scalar(r['data'].get('PARENT')) for r in records if r['type']=='GROUP'}
    def ancestor(ledger, ancestor_name):
        parent=scalar(ledger.get('PARENT'))
        for _ in range(50):
            if normalized(parent)==normalized(ancestor_name): return True
            parent=groups.get(normalized(parent))
            if not parent: return False
        return False
    if not ancestor(bank,'Bank Accounts'): raise ValueError('The bank ledger must belong to the discovered Bank Accounts group.')
    family=selection.get('family') or ('payment' if row['amount_cents']<0 else 'receipt')
    if family not in ('payment','receipt','contra') or (family!='contra' and family!=('payment' if row['amount_cents']<0 else 'receipt')):
        raise ValueError('Money out is a Payment, money in a Receipt; a transfer between own accounts is a Contra.')
    if family=='contra' and not (ancestor(counter,'Bank Accounts') or ancestor(counter,'Cash-in-Hand')):
        raise ValueError('A Contra moves money between the client\'s own bank or cash ledgers.')
    allocation=None
    if selection.get('cost_centre_guid') or selection.get('cost_category_guid'):
        centre=selected('COSTCENTRE','cost_centre_guid')
        category=selected('COSTCATEGORY','cost_category_guid')
        if normalized(scalar(centre.get('CATEGORY')))!=normalized(name(category)):
            raise ValueError('The selected cost centre does not belong to the selected category.')
        if scalar(counter.get('ISCOSTCENTRESON')).casefold()!='yes':
            raise ValueError('The Other-side ledger must enable cost centres in Tally for this branch.')
        allocation={'centre':name(centre),'category':name(category),'centre_guid':scalar(centre.get('GUID')),
                    'category_guid':scalar(category.get('GUID'))}
    if name(counter)==name(bank): raise ValueError('Bank and Other-side ledgers must differ.')
    base=family
    types=[r['data'] for r in records if r['type']=='VOUCHERTYPE']
    bases=base_types(types)
    voucher=selected('VOUCHERTYPE','voucher_type_guid')
    if normalized(bases.get(name(voucher).casefold()))!=base or scalar(voucher.get('ISACTIVE')).casefold()=='no':
        raise ValueError(f'The selected voucher type must be an active {base.title()} type.')
    def identities(master):
        return {key:scalar(master.get(key)) for key in ('GUID','PARENT','ALTERID')}
    lines=None
    if selection.get('lines'):
        # Several counter lines (charges with GST, TDS) split the one bank amount exactly.
        if family=='contra': raise ValueError('A Contra has one counter bank or cash ledger.')
        lines,total,names=[],0,{name(bank)}
        for line in selection['lines']:
            ledger=one([r['data'] for r in records if r['type']=='LEDGER' and scalar(r['data'].get('GUID'))==line.get('ledger_guid')],
                       'Each line must select one discovered ledger.')
            cents=int(Decimal(str(line['amount']))*100) if isinstance(line.get('amount'),(int,float)) else 0
            if cents<=0 or Decimal(str(line['amount']))*100!=cents or name(ledger) in names:
                raise ValueError('Each line needs a positive exact amount and a distinct ledger.')
            names.add(name(ledger))
            total+=cents
            allocation=None
            if line.get('cost_centre_guid') or line.get('cost_category_guid'):
                centre=one([r['data'] for r in records if r['type']=='COSTCENTRE' and scalar(r['data'].get('GUID'))==line.get('cost_centre_guid')],'Select one discovered cost centre.')
                category=one([r['data'] for r in records if r['type']=='COSTCATEGORY' and scalar(r['data'].get('GUID'))==line.get('cost_category_guid')],'Select one discovered cost category.')
                if normalized(scalar(centre.get('CATEGORY')))!=normalized(name(category)) or scalar(ledger.get('ISCOSTCENTRESON')).casefold()!='yes':
                    raise ValueError('Cost allocations need a centre of the selected category on a ledger that enables them.')
                allocation={'centre':name(centre),'category':name(category),'centre_guid':scalar(centre.get('GUID')),'category_guid':scalar(category.get('GUID'))}
            lines.append({'ledger':name(ledger),'amount_cents':cents,'allocation':allocation,'identity':identities(ledger)})
        if total!=abs(row['amount_cents']):
            raise ValueError('The lines must add up exactly to the bank amount.')
        if lines[0]['ledger']!=name(counter):
            raise ValueError('The counter ledger must be the first line.')
    return {
        'family':family,'lines':lines,'company':company['company'],'company_guid':company['company_guid'],'port':company['port'],
        'data':{**row,'bank_ledger':name(bank),'counter_ledger':name(counter)},'allocation':allocation,
        'voucher_type':{'NAME':name(voucher),**identities(voucher)},
        'references':{'company_guid':company['company_guid'],'ledgers':{name(m):identities(m) for m in (bank,counter)}}}
