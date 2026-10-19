"""Bounded deterministic bank-file adapter. Unknown layouts remain exceptions.

Header synonyms describe file conventions, never customer branches or ledgers.
One immutable row identity is shared by preview, overlapping files and writes.
"""
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook

from .excel import open_workbook

ALIASES = {
    'date': {'date','transactiondate','txndate','valuedate','postingdate'},
    'reference': {'reference','referenceno','transactionid','transactionreference','chequeno','chequenumber','chqrefno','refno','utr'},
    'debit': {'debit','debitamount','withdrawal','withdrawals','withdrawalamount','dr'},
    'credit': {'credit','creditamount','deposit','deposits','depositamount','cr'},
    'amount': {'amount','transactionamount','signedamount'},
    'balance': {'balance','runningbalance','closingbalance','availablebalance'},
    'branch': {'branch'},
    'narration': {'narration','description','particulars','remarks','transactiondetails'},
}


def normalized(value):
    return ' '.join(str(value or '').split()).casefold()


def money(value):
    raw = str(value).strip().replace(',', '').replace('₹', '').strip()
    suffix = re.search(r'\s*(Dr|Cr)$', raw, re.I)
    if suffix:
        raw = raw[:suffix.start()].strip()
    if raw.startswith('(') and raw.endswith(')'):
        raw = '-' + raw[1:-1]
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount != amount.quantize(Decimal('.01')) or abs(amount) > Decimal('99999999999'):
            raise ValueError('Unsupported monetary precision or value.')
        return int(abs(amount) * (-100 if suffix.group(1).lower() == 'dr' else 100)) if suffix else int(amount * 100)
    except InvalidOperation as error:
        raise ValueError('Invalid monetary value.') from error


def row_identity(row, occurrence):
    values = [normalized(row.get('reference')), row['date'], row['amount_cents'], row['balance_cents'], occurrence]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _tables(content, suffix):
    if suffix == '.csv':
        try: text = content.decode('utf-8-sig')
        except UnicodeDecodeError: text = content.decode('cp1252')
        try: dialect = csv.Sniffer().sniff(text[:16000], delimiters=',;\t')
        except csv.Error: dialect = csv.excel
        return [('', list(csv.reader(io.StringIO(text), dialect)), set())]
    if suffix != '.xlsx':
        raise ValueError('Use .csv or .xlsx; legacy .xls requires conversion in Excel.')
    formulas = open_workbook(content)
    values = load_workbook(io.BytesIO(content), data_only=True)
    result = []
    for sheet in values:
        if sheet.max_row > 10050 or sheet.max_column > 100:
            raise ValueError('Select a statement with at most 10,000 transactions and 100 columns.')
        missing = {(cell.row, cell.column) for cells in formulas[sheet.title] for cell in cells
                   if cell.data_type == 'f' and sheet.cell(cell.row, cell.column).value is None}
        result.append((sheet.title, list(sheet.values), missing))
    return result


def parse_statement(content, suffix, settings):
    try: tables = _tables(content, suffix.lower())
    except (ValueError, UnicodeError, csv.Error):
        return [{'row': 0, 'sheet': '', 'code': 'statement_format', 'reason': 'Use a readable CSV or XLSX statement; convert legacy XLS files in Excel.'}]
    rows = []
    occurrences = Counter()
    for sheet, table, formulas in tables:
        header = None
        for index, cells in enumerate(table[:50]):
            mapping, ambiguous = {}, False
            for column, value in enumerate(cells):
                name = re.sub(r'[^a-z0-9]', '', normalized(value))
                for field, aliases in ALIASES.items():
                    if name in aliases:
                        ambiguous |= field in mapping
                        mapping[field] = column
            if {'date','branch','balance'} <= mapping.keys() and ('amount' in mapping or {'debit','credit'} <= mapping.keys()):
                if not ambiguous and not ('amount' in mapping and ('debit' in mapping or 'credit' in mapping)):
                    header = index, mapping
                break
        if header is None:
            rows.append({'row': 0, 'sheet': sheet, 'code': 'statement_columns', 'reason': 'Column layout is ambiguous. Use Date, Branch, Balance and Amount, or separate Debit and Credit headers.'})
            continue
        start, mapping = header
        previous = money(settings['opening_balance']) if settings.get('opening_balance') else None
        for number, cells in enumerate(table[start + 1:], start + 2):
            if len(rows) >= 10000:
                raise ValueError('Select at most 10,000 transaction rows.')
            if not any(value is not None and str(value).strip() for value in cells): continue
            get = lambda key: cells[mapping[key]] if key in mapping and mapping[key] < len(cells) else None
            label = normalized(' '.join(str(v or '') for v in cells[:3]))
            if label.startswith(('opening balance', 'balance brought forward')):
                try: previous = money(get('balance'))
                except ValueError: previous = None
                continue
            if label.startswith(('closing balance', 'total transactions')): continue
            row = {'row': number, 'sheet': sheet, 'branch': str(get('branch') or '').strip(),
                   'reference': str(get('reference') or '').strip(), 'narration': str(get('narration') or '').strip()[:500]}
            balance = None
            try:
                if any((number, column + 1) in formulas for column in mapping.values()):
                    row.update(code='statement_formula', reason='A formula has no cached value. Recalculate and save the source in Excel.')
                    raise ValueError()
                raw_date = get('date')
                if isinstance(raw_date, (date, datetime)): observed = raw_date.date() if isinstance(raw_date, datetime) else raw_date
                else:
                    raw_date = str(raw_date or '').strip()
                    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_date): observed = date.fromisoformat(raw_date)
                    else:
                        fmt = settings.get('date_format', 'dmy')
                        pattern = '%d/%m/' if fmt == 'dmy' else '%m/%d/' if fmt == 'mdy' else None
                        if not pattern: raise ValueError()
                        value = raw_date.replace('-', '/')
                        observed = datetime.strptime(value, pattern + ('%y' if len(value.split('/')[-1]) == 2 else '%Y')).date()
                row['date'] = observed.isoformat()
                if 'amount' in mapping: amount = money(get('amount'))
                else:
                    debit, credit = (money(get(key)) if get(key) not in (None, '') else 0 for key in ('debit','credit'))
                    if debit < 0 or credit < 0 or (debit and credit): raise ValueError()
                    amount = credit - debit
                if not amount: raise ValueError()
                row['amount_cents'] = amount
                balance = money(get('balance'))
                row['balance_cents'] = balance
                if previous is None or previous + amount != balance:
                    row.update(code='statement_balance', reason='The running balance cannot be verified against the preceding balance and transaction.')
                key = row_identity(row, 0)
                occurrences[key] += 1
                row['identity'] = row_identity(row, occurrences[key])
            except (ValueError, TypeError, OverflowError):
                row.setdefault('code', 'statement_balance' if 'amount_cents' in row else 'statement_value')
                row.setdefault('reason', 'A required date, amount or running balance is missing or invalid. Correct the original statement and run it again.')
            rows.append(row)
            previous = balance
    return rows
