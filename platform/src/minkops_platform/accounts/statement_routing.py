"""Branch lookup and pluggable counter-ledger strategy over pinned discovery."""
from minkops_connectors.statement import normalized
from .client_context import books_beginning, master_lookup
from .supplier_gst import scalar
from .voucher_types import base_types


def name(master):
    return scalar(master.get('@_NAME') or master.get('NAME'))


def one(values, message):
    if len(values) != 1: raise ValueError(message)
    return values[0]


def named(records, kind, value):
    return [r['data'] for r in records if r['type']==kind and normalized(name(r['data']))==normalized(value)]


def single_counter(company, records, settings):
    return one(named(records,'LEDGER',settings.get('other_side_ledger')), 'Choose a discovered Other-side ledger for this company.')


COUNTERS = {'single': single_counter}


def route(row, companies, settings):
    matches=[]
    for company in companies:
        records=master_lookup(company)['records']
        if normalized(company['company'])==normalized(row['branch']):
            matches.append((company,records,'COMPANY',company['identity']))
        matches.extend((company,records,r['type'],r['data']) for r in records
            if r['type'] in ('LEDGER','GROUP','COSTCENTRE','COSTCATEGORY') and normalized(name(r['data']))==normalized(row['branch']))
    company,records,kind,master=one(matches,'The branch must match exactly one discovered company, ledger, group, cost centre or category.')
    beginning=books_beginning(company['identity'])
    if beginning and row['date']<beginning: raise ValueError('The transaction date precedes the company books beginning date.')
    strategy=COUNTERS.get(settings.get('counter_mode','single'))
    if strategy is None: raise ValueError('Unsupported Other-side ledger strategy.')
    counter=strategy(company,records,settings)
    bank=one(named(records,'LEDGER',settings.get('bank_ledgers',{}).get(company['company_guid'])), 'Choose the discovered bank ledger for this company.')
    groups={normalized(name(r['data'])):scalar(r['data'].get('PARENT')) for r in records if r['type']=='GROUP'}
    def ancestor(ledger, ancestor_name):
        parent=scalar(ledger.get('PARENT'))
        for _ in range(50):
            if normalized(parent)==normalized(ancestor_name): return True
            parent=groups.get(normalized(parent))
            if not parent: return False
        return False
    if not ancestor(bank,'Bank Accounts'): raise ValueError('The bank ledger must belong to the discovered Bank Accounts group.')
    allocation=None
    if kind=='LEDGER': counter=master
    elif kind=='GROUP':
        counter=one([r['data'] for r in records if r['type']=='LEDGER' and ancestor(r['data'],name(master)) and name(r['data'])!=name(bank)],
            'This branch group needs exactly one posting ledger; otherwise handle the row manually.')
    elif kind in ('COSTCENTRE','COSTCATEGORY'):
        centre=master if kind=='COSTCENTRE' else one([r['data'] for r in records if r['type']=='COSTCENTRE'
            and normalized(scalar(r['data'].get('CATEGORY')))==normalized(name(master))], 'This branch category needs exactly one cost centre.')
        category=one(named(records,'COSTCATEGORY',scalar(centre.get('CATEGORY'))), 'The cost centre category is missing or ambiguous.')
        if scalar(counter.get('ISCOSTCENTRESON')).casefold()!='yes':
            raise ValueError('The Other-side ledger must enable cost centres in Tally for this branch.')
        allocation={'centre':name(centre),'category':name(category),'centre_guid':scalar(centre.get('GUID')),
                    'category_guid':scalar(category.get('GUID'))}
    if name(counter)==name(bank): raise ValueError('Bank and Other-side ledgers must differ.')
    base='payment' if row['amount_cents']<0 else 'receipt'
    types=[r['data'] for r in records if r['type']=='VOUCHERTYPE']
    bases=base_types(types)
    candidates=[r for r in types if normalized(bases.get(name(r).casefold()))==base and scalar(r.get('ISACTIVE')).casefold()!='no']
    selected=settings.get('voucher_types',{}).get(company['company_guid'],{}).get(base)
    if selected: candidates=[r for r in candidates if scalar(r.get('GUID'))==selected]
    voucher=one(candidates,f'Choose exactly one active {base.title()} voucher type from Source Discovery.')
    identities=lambda master:{key:scalar(master.get(key)) for key in ('GUID','PARENT','ALTERID')}
    return {'company':company['company'],'company_guid':company['company_guid'],'port':company['port'],'matched_kind':kind,
        'data':{**row,'bank_ledger':name(bank),'counter_ledger':name(counter)},'allocation':allocation,
        'voucher_type':{'NAME':name(voucher),**identities(voucher)},
        'references':{'company_guid':company['company_guid'],'ledgers':{name(m):identities(m) for m in (bank,counter)}}}
