import io
from openpyxl import Workbook
from minkops_connectors.statement import parse_statement


def parse(text, **settings):
    return parse_statement(text.encode('utf-8-sig'), '.csv', {'date_format': 'dmy', **settings})


def test_split_columns_balance_chain_and_occurrence_identity():
    text = 'Bank statement\nDate,Reference,Debit,Credit,Balance,Branch\nOpening balance,,,,1000,\n01/10/26,R1,100,,900, Test Company \n02/10/26,R2,,50,950,Test Company\n'
    rows = parse(text)
    assert [r['amount_cents'] for r in rows] == [-10000, 5000]
    assert not any(r.get('code') for r in rows)
    assert rows[0]['date'] == '2026-10-01'
    assert parse(text)[0]['identity'] == rows[0]['identity']
    # An overlapping download retains a row's identity independently of position.
    overlap = parse('Date,Reference,Amount,Balance,Branch\nOpening balance,,,900,\n02/10/26,R2,50,950,Test Company\n')
    assert overlap[0]['identity'] == rows[1]['identity']


def test_missing_and_bad_balance_never_become_ready():
    rows = parse('Date,Reference,Amount,Balance,Branch\n01/10/26,A,-10,90,Test\n02/10/26,B,-10,79,Test\n03/10/26,C,-10,,Test\n')
    assert [r['code'] for r in rows] == ['statement_balance', 'statement_balance', 'statement_balance']


def test_ambiguous_headers_and_legacy_excel_fail_closed():
    assert parse('Date,Date,Amount,Balance,Branch\n1,2,3,4,5')[0]['code'] == 'statement_columns'
    assert parse_statement(b'legacy', '.xls', {})[0]['code'] == 'statement_format'


def test_cp1252_and_uncached_formulas_are_visible():
    csv = 'Date,Reference,Amount,Balance,Branch\nOpening balance,,,100,\n01/10/26,Café,-10,90,Test\n'.encode('cp1252')
    assert parse_statement(csv, '.csv', {'date_format': 'dmy'})[0]['reference'] == 'Café'
    book = Workbook(); sheet = book.active
    sheet.append(['Date','Reference','Amount','Balance','Branch'])
    sheet.append(['Opening balance',None,None,100,None])
    sheet.append(['01/10/26','A',-10,90,'=A1'])
    buffer = io.BytesIO(); book.save(buffer)
    assert parse_statement(buffer.getvalue(), '.xlsx', {'date_format':'dmy'})[0]['code'] == 'statement_formula'

