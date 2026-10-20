import io
from collections import Counter
from datetime import date

import pytest
from openpyxl import Workbook

from minkops_connectors.statement import apply_layout, header_signature, preview, read_tables, signatures


def table(text):
    return read_tables(text.encode('utf-8-sig'), '.csv')[0][1]


def layout(amount=None, *, order='dmy', row_order='oldest_first', balance=5, reference=2, narration=(), account=None,
           hint=None, rows=None):
    return {'columns': {'date': {'column': 1, 'order': order},
                        'amount': amount or {'mode': 'debit_credit', 'debit': 3, 'credit': 4},
                        'balance': {'column': balance} if balance else None,
                        'reference': {'column': reference} if reference else None,
                        'narration': {'columns': list(narration)},
                        'account': {'column': account} if account else None,
                        'routing_hint': {'column': hint, 'label': 'Branch'} if hint else None},
            'row_order': row_order, 'rows': rows or {}}


OPENING = {'opening': [{'column': 1, 'starts_with': 'Opening balance'}]}
OLD = 'Bank statement\nDate,Reference,Debit,Credit,Balance,Branch\nOpening balance,,,,1000,\n01/10/26,R1,100,,900, Test Company \n02/10/26,R2,,50,950,Test Company\n'


def test_rows_keep_the_identities_the_old_parser_gave_them():
    rows, proof = apply_layout(table(OLD), layout(hint=6, rows=OPENING), 1)
    assert [r['identity'] for r in rows] == [
        'e8172aa88010993502df5a499a6fe61a22131015e36096b8318b13b8d5ccf8d4',
        '0f322ee2e183b9cd663a39fcad4e5eb61b33d8f7a5d071a2a738bcd868e3061f']
    assert [r['amount_cents'] for r in rows] == [-10000, 5000]
    assert (rows[0]['date'], rows[0]['branch'], proof['amounts']) == ('2026-10-01', 'Test Company', True)
    assert proof['date_order'] is False  # 01/10 and 02/10 also read as 10 January and 10 February.
    repeated = table('Date,Reference,Amount,Balance,Branch\nOpening balance,,,100,\n01/10/26,A,-10,90,Test\n01/10/26,A,-10,90,Test\n')
    rows, _ = apply_layout(repeated, layout({'mode': 'signed', 'column': 3}, balance=4, rows=OPENING), 0)
    assert [r['identity'] for r in rows] == [
        '37079c038892d579caf7c665e095fed684aa5a1a9bfca3ff4dae24c3d6177688',
        'e30f23dc8925ebfd480c0c0fb1ed2821ca5ff9afa0e1628b567e1c64045ad189']
    assert rows[1]['code'] == 'statement_balance'  # A repeated row cannot chain: 90 then 90 after -10.


def test_a_dual_date_sbi_export_reads_through_its_declared_transaction_date():
    sbi = table('Account Statement\nTxn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance\n'
                '01 Oct 2026,02 Oct 2026,NEFT charges,UTR1,17.70,,982.30\n03 Oct 2026,03 Oct 2026,Interest,,,5.00,987.30\n')
    rows, proof = apply_layout(sbi, layout({'mode': 'debit_credit', 'debit': 5, 'credit': 6}, balance=7, reference=4, narration=(3,)), 1)
    assert [(r['date'], r['amount_cents'], r['narration']) for r in rows] == [('2026-10-01', -1770, 'NEFT charges'), ('2026-10-03', 500, 'Interest')]
    assert proof['amounts'] and proof['date_order']


def test_newest_first_files_chain_in_their_accumulation_order():
    newest = table('Date,Ref,Withdrawal Amt.,Deposit Amt.,Closing Balance\n03/10/26,C,,20,1010\n02/10/26,B,10,,990\n01/10/26,A,,0.50,1000\n')
    rows, proof = apply_layout(newest, layout(row_order='newest_first'), 0)
    assert not any(r.get('code') for r in rows) and proof['amounts']
    rows, proof = apply_layout(newest, layout(), 0)
    assert not proof['amounts'] and any(r.get('code') == 'statement_balance' for r in rows)


def test_an_amount_with_a_separate_dr_cr_column_and_suffixed_balances():
    indicator = table('Date,Narration,Amount (INR),Dr/Cr,Balance\n01/10/26,Rent,"1,00,000.00",DR,"4,00,000.00 Cr"\n02/10/26,Sale,500,CR,"4,00,500.00 Cr"\n')
    spec = layout({'mode': 'indicator', 'column': 3, 'indicator': 4, 'debit_values': ['DR'], 'credit_values': ['CR']},
                  reference=None, narration=(2,))
    rows, proof = apply_layout(indicator, spec, 0)
    assert [r['amount_cents'] for r in rows] == [-10000000, 50000] and proof['amounts']
    unknown = table('Date,Narration,Amount,Dr/Cr,Balance\n01/10/26,Rent,10,??,90\n')
    assert apply_layout(unknown, spec, 0)[0][0]['code'] == 'statement_value'


def test_a_mixed_bank_daily_sheet_proves_each_account_separately():
    mixed = table('Date,Bank Account,Ref,Debit,Credit,Balance\n'
                  '01/10/26,HDFC 1234,H1,100,,900\n01/10/26,ICICI 5678,I1,,50,2050\n'
                  '01/10/26,HDFC 1234,H2,,10,910\n01/10/26,ICICI 5678,I2,25,,2025\n01/10/26,SBI 9999,S1,5,,95\n')
    spec = layout({'mode': 'debit_credit', 'debit': 4, 'credit': 5}, balance=6, reference=3, account=2)
    rows, proof = apply_layout(mixed, spec, 0)
    assert not any(r.get('code') for r in rows)
    assert proof['accounts'] == ['HDFC 1234', 'ICICI 5678'] and proof['amounts']
    assert {r['account'] for r in rows} == {'HDFC 1234', 'ICICI 5678', 'SBI 9999'}


def test_single_row_accounts_read_through_the_layout_but_cannot_prove_it():
    single = table('Date,Bank Account,Ref,Debit,Credit,Balance\n15/10/26,HDFC 1234,H1,100,,900\n15/10/26,ICICI 5678,I1,,50,2050\n')
    rows, proof = apply_layout(single, layout({'mode': 'debit_credit', 'debit': 4, 'credit': 5}, balance=6, reference=3, account=2), 0)
    assert not any(r.get('code') for r in rows)  # Implied openings: values are read, not guessed.
    assert proof['amounts'] is False and proof['date_order'] is True


def test_without_a_balance_column_nothing_can_be_proven():
    rows, proof = apply_layout(table('Date,Ref,Amount\n01/10/26,A,-10\n02/10/26,B,20\n'),
                               layout({'mode': 'signed', 'column': 3}, balance=None), 0)
    assert [r['amount_cents'] for r in rows] == [-1000, 2000] and not any(r.get('code') for r in rows)
    assert proof['amounts'] is False and len(proof['samples']) == 2


def test_a_closing_row_must_equal_the_last_running_balance():
    closing = table('Date,Ref,Debit,Credit,Balance\nOpening balance,,,,1000\n01/10/26,A,100,,900\nClosing balance,,,,950\n')
    rows, _ = apply_layout(closing, layout(rows={**OPENING, 'closing': [{'column': 1, 'starts_with': 'Closing balance'}]}), 0)
    assert rows[-1]['code'] == 'statement_closing'


def test_date_order_is_proven_only_by_the_dates_themselves():
    early = table('Date,Ref,Debit,Credit,Balance\n03/04/26,A,1,,99\n05/04/26,B,1,,98\n')
    assert apply_layout(early, layout(), 0, today=date(2026, 10, 20))[1]['date_order'] is False
    late_day = table('Date,Ref,Debit,Credit,Balance\n03/04/26,A,1,,99\n25/04/26,B,1,,98\n')
    assert apply_layout(late_day, layout(), 0, today=date(2026, 10, 20))[1]['date_order'] is True
    # Read month-first, 11/10 would be 10 November: after the file was uploaded.
    recent = table('Date,Ref,Debit,Credit,Balance\n11/10/26,A,1,,99\n12/10/26,B,1,,98\n')
    assert apply_layout(recent, layout(), 0, today=date(2026, 10, 20))[1]['date_order'] is True


def test_page_headers_totals_and_trailing_text_are_skipped_as_declared():
    paged = table('Date,Ref,Debit,Credit,Balance\n01/10/26,A,100,,900\nDate,Ref,Debit,Credit,Balance\n02/10/26,B,,50,950\n'
                  'Total,,100,50,\nThis is a computer generated statement\n')
    rules = {'ignore': [{'repeat_header': True}, {'column': 1, 'starts_with': 'Total'}],
             'ends_at': [{'column': 1, 'starts_with': 'This is a computer'}]}
    rows, proof = apply_layout(paged, layout(rows=rules), 0)
    assert [r['reference'] for r in rows] == ['A', 'B'] and proof['amounts']


def test_header_signatures_find_a_known_layout_after_any_preamble():
    one = table('Statement for 1234\nPeriod 01/10/26 to 31/10/26\nDate,Ref,Debit,Credit,Balance\n01/10/26,A,1,,9\n')
    two = table('Statement for 9876\nDate,Ref,Debit,Credit,Balance\n02/10/26,B,1,,8\n')
    signature = header_signature(['Date', 'Ref', 'Debit', 'Credit', 'Balance'])
    assert signatures(one)[signature] == 2 and signatures(two)[signature] == 1
    assert preview(one)[0] == {'row': 1, 'cells': ['Statement for 1234']}


def test_uncached_formulas_and_legacy_files_fail_closed():
    book = Workbook(); sheet = book.active
    sheet.append(['Date', 'Reference', 'Amount', 'Balance'])
    sheet.append(['01/10/26', 'A', -10, '=A1'])
    buffer = io.BytesIO(); book.save(buffer)
    [(name, rows, formulas)] = read_tables(buffer.getvalue(), '.xlsx')
    parsed, _ = apply_layout(rows, layout({'mode': 'signed', 'column': 3}, balance=4), 0, sheet=name, formulas=formulas,
                             occurrences=Counter())
    assert parsed[0]['code'] == 'statement_formula'
    with pytest.raises(ValueError):
        read_tables(b'legacy', '.xls')
    cp = 'Date,Reference,Amount,Balance\n01/10/26,Café,-10,90\n'.encode('cp1252')
    assert read_tables(cp, '.csv')[0][1][1][1] == 'Café'
