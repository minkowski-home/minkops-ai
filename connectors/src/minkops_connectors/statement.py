"""Bank-file adapter: apply a declared layout, then prove it with the balances.

Recognising a statement's structure is the AI's (a declarative layout per sheet:
header row, column roles, date order, sign convention, row order, summary rows).
This module never guesses a layout. It reads every value through the declared
layout and proves it: per account, each printed running balance must equal the
previous balance plus the signed transaction, and date order must be fixed by
the dates themselves. Values are never transcribed by the model, and one
immutable row identity is shared by preview, overlapping files and writes.
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

MAX_ROWS = 10_000
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
ORDERS = {"dmy": (0, 1, 2), "mdy": (1, 0, 2), "ymd": (2, 1, 0)}


def normalized(value):
    return ' '.join(str(value or '').split()).casefold()


def money(value):
    raw = str(value).strip().replace(',', '').replace('₹', '').strip()
    raw = re.sub(r'^(?:inr|rs\.?)\s*', '', raw, flags=re.I)
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


def read_tables(content, suffix):
    """[(sheet, rows, uncached formula cells)] from CSV or XLSX; ValueError otherwise."""
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
        if sheet.max_row > MAX_ROWS + 50 or sheet.max_column > 100:
            raise ValueError('Select a statement with at most 10,000 transactions and 100 columns.')
        missing = {(cell.row, cell.column) for cells in formulas[sheet.title] for cell in cells
                   if cell.data_type == 'f' and sheet.cell(cell.row, cell.column).value is None}
        result.append((sheet.title, list(sheet.values), missing))
    return result


def cell_text(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return ' '.join(str(value if value is not None else '').split())


def header_signature(cells):
    """A layout's identity: its header cells and their positions, nothing else."""
    named = [[index, normalized(cell)] for index, cell in enumerate(cells) if normalized(cell)]
    return hashlib.sha256(json.dumps(named, ensure_ascii=False).encode()).hexdigest()


def signatures(table, limit=60):
    """Candidate header rows: {signature: zero-based row index} for label-like rows."""
    found = {}
    for index, cells in enumerate(table[:limit]):
        labels = [c for c in cells if isinstance(c, str) and c.strip() and not re.fullmatch(r'[\d.,\s₹()-]+', c)]
        if len(labels) >= 2:
            found.setdefault(header_signature(cells), index)
    return found


def preview(table, first=60, last=15):
    """Bounded text view of a sheet for layout inference; 1-based row numbers."""
    rows = list(enumerate(table, 1))
    chosen = rows if len(rows) <= first + last else [*rows[:first], *rows[-last:]]
    return [{'row': number, 'cells': [cell_text(v) for v in cells]} for number, cells in chosen
            if any(cell_text(v) for v in cells)]


def parse_date(value, order):
    """A calendar date read through a declared order; ValueError when it does not read."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return date.fromisoformat(text)
    parts = [p for p in re.split(r'[\s/.\-]+', text) if p]
    if len(parts) != 3:
        raise ValueError('Unreadable date.')
    named = [i for i, p in enumerate(parts) if p[:3].casefold() in MONTHS and not p.isdigit()]
    if named:
        month = MONTHS[parts[named[0]][:3].casefold()]
        rest = [int(p) for i, p in enumerate(parts) if i != named[0]]
        day, year = (rest[1], rest[0]) if named[0] == 2 else (rest[0], rest[1])
    else:
        if order not in ORDERS:
            raise ValueError('Unreadable date order.')
        d, m, y = (int(parts[i]) for i in ORDERS[order])
        day, month, year = d, m, y
    if year < 100:
        year += 2000
    return date(year, month, day)


def _ambiguous(value):
    """A numeric text date whose day and month could be swapped."""
    if isinstance(value, (date, datetime)):
        return False
    parts = [p for p in re.split(r'[\s/.\-]+', str(value or '').strip()) if p]
    return len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) <= 2 and len(parts[1]) <= 2


def _matches(cells, rules):
    for rule in rules or []:
        if rule.get('repeat_header'):
            continue
        column = rule.get('column')
        value = normalized(cells[column - 1]) if column and column - 1 < len(cells) else normalized(' '.join(cell_text(c) for c in cells))
        if value.startswith(normalized(rule.get('starts_with'))):
            return True
    return False


def apply_layout(table, layout, header_index, *, sheet='', formulas=frozenset(), occurrences=None, today=None):
    """Canonical rows through a declared layout, proven per account.

    Returns (rows, proof). Rows carry a `code` when a value does not read or a
    balance does not chain. `proof` says whether the layout itself is proven:
    `amounts` (some account with at least two rows chains completely) and
    `date_order` (no numeric text date could be read with day and month swapped).
    """
    columns, rules = layout['columns'], layout.get('rows', {})
    occurrences = Counter() if occurrences is None else occurrences
    header = [normalized(c) for c in table[header_index]]
    amount_mode = columns['amount']['mode']
    order = columns['date'].get('order', 'native')
    rows, ambiguous_dates, closings = [], [], []

    def get(cells, spec):
        column = (spec or {}).get('column')
        return cells[column - 1] if column and column - 1 < len(cells) else None

    for number, cells in enumerate(table[header_index + 1:], header_index + 2):
        if not any(v is not None and str(v).strip() for v in cells):
            continue
        if any(r.get('repeat_header') for r in rules.get('ignore', [])) and [normalized(c) for c in cells] == header:
            continue
        if _matches(cells, rules.get('ends_at')):
            break
        if _matches(cells, rules.get('ignore')):
            continue
        account = cell_text(get(cells, columns.get('account')))
        if _matches(cells, rules.get('opening')) or _matches(cells, rules.get('closing')):
            kind = 'opening' if _matches(cells, rules.get('opening')) else 'closing'
            try:
                (rows if kind == 'opening' else closings).append({'row': number, 'sheet': sheet, 'account': account,
                    'kind': kind, 'balance_cents': money(get(cells, columns.get('balance')))})
            except (ValueError, TypeError):
                pass
            continue
        if len(rows) >= MAX_ROWS:
            raise ValueError('Select at most 10,000 transaction rows.')
        narration = ' '.join(cell_text(cells[c - 1]) for c in (columns.get('narration') or {}).get('columns', []) if c - 1 < len(cells))
        row = {'row': number, 'sheet': sheet, 'account': account,
               'branch': cell_text(get(cells, columns.get('routing_hint'))),
               'reference': cell_text(get(cells, columns.get('reference'))), 'narration': narration.strip()[:500]}
        try:
            used = [c for spec in columns.values() for c in ([spec['column']] if isinstance(spec, dict) and spec.get('column') else [])]
            if any((number, c) in formulas for c in used):
                row.update(code='statement_formula', reason='A formula has no cached value. Recalculate and save the source in Excel.')
                raise ValueError()
            raw_date = get(cells, columns['date'])
            if order in ('dmy', 'mdy') and _ambiguous(raw_date):
                ambiguous_dates.append(raw_date)
            row['date'] = parse_date(raw_date, order).isoformat()
            if amount_mode == 'debit_credit':
                debit, credit = (money(get(cells, {'column': columns['amount'][k]}))
                                 if get(cells, {'column': columns['amount'][k]}) not in (None, '') else 0 for k in ('debit', 'credit'))
                if debit < 0 or credit < 0 or (debit and credit): raise ValueError()
                amount = credit - debit
            elif amount_mode == 'signed':
                amount = money(get(cells, {'column': columns['amount']['column']}))
                if columns['amount'].get('negative') == 'credit':
                    amount = -amount
            else:
                value = abs(money(get(cells, {'column': columns['amount']['column']})))
                flag = normalized(get(cells, {'column': columns['amount']['indicator']}))
                if flag in {normalized(v) for v in columns['amount'].get('debit_values', [])}: amount = -value
                elif flag in {normalized(v) for v in columns['amount'].get('credit_values', [])}: amount = value
                else: raise ValueError()
            if not amount: raise ValueError()
            row['amount_cents'] = amount
            row['balance_cents'] = money(get(cells, columns['balance'])) if columns.get('balance') else None
            key = row_identity(row, 0)
            occurrences[key] += 1
            row['identity'] = row_identity(row, occurrences[key])
        except (ValueError, TypeError, OverflowError, KeyError):
            row.setdefault('code', 'statement_value')
            row.setdefault('reason', 'A required date, amount or running balance is missing or invalid. Correct the original statement and run it again.')
        rows.append(row)

    # Prove the reading per account, in the order the balances accumulate.
    chain = rows if layout.get('row_order', 'oldest_first') == 'oldest_first' else rows[::-1]
    balances, proven_accounts, chained, broken = {}, set(), Counter(), set()
    for row in chain:
        account = row['account']
        if row.get('kind') == 'opening':
            balances[account] = row['balance_cents']
            continue
        if row.get('code') or row.get('balance_cents') is None:
            if columns.get('balance') and not row.get('code'):
                row.update(code='statement_balance', reason='The running balance is missing.')
            broken.add(account)
            continue
        previous = balances.get(account, row['balance_cents'] - row['amount_cents'])
        if previous + row['amount_cents'] != row['balance_cents']:
            row.update(code='statement_balance', reason='The running balance cannot be verified against the preceding balance and transaction.')
            broken.add(account)
        else:
            chained[account] += 1
        balances[account] = row['balance_cents']
    for account, count in chained.items():
        if count >= 2 and account not in broken:
            proven_accounts.add(account)
    findings = []
    for closing in closings:
        if balances.get(closing['account']) != closing['balance_cents']:
            findings.append({'row': closing['row'], 'sheet': sheet, 'code': 'statement_closing',
                             'reason': 'The printed closing balance differs from the last running balance; a transaction may be missing.'})
    alternative = {'dmy': 'mdy', 'mdy': 'dmy'}.get(order)
    date_proven = not ambiguous_dates or _order_forced(ambiguous_dates, alternative, today)
    transactions = [r for r in rows if r.get('kind') != 'opening']
    proof = {'amounts': bool(columns.get('balance')) and bool(proven_accounts), 'date_order': date_proven,
             'accounts': sorted(proven_accounts), 'samples': [{k: r.get(k) for k in ('date', 'amount_cents', 'balance_cents', 'account', 'narration')}
                                                               for r in transactions[:3] if not r.get('code')]}
    return [*transactions, *findings], proof


def _order_forced(values, alternative, today):
    """Would reading these dates the other way be impossible (or in the future)?"""
    for value in values:
        try:
            other = parse_date(value, alternative)
        except ValueError:
            return True
        if today and other > today:
            return True
    return False

