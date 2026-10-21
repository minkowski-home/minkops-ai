"""Known source bytes retain verified accounting; native readback still decides."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from minkops_platform.accounts.tally_writes import reuse_verified_source


def inputs():
    record = {'source_file_id': 'new', 'company_guid': 'company', 'operation': 'append',
              'document': {'number': 'invoice', 'total': 118}, 'findings': [], 'exception_codes': [],
              'voucher': {'family': 'purchase', 'lines': [{'ledger_guid': 'new-guess'}]}, 'notes': []}
    prior = {**deepcopy(record), 'voucher': {'family': 'purchase', 'lines': [{'ledger_guid': 'verified'}]}}
    run = {'id': 'run', 'tenant_id': 'tenant', 'actor_id': 'actor', 'config': {
        'tally_target': {'device_id': 'pc'}, 'file_provenance': [{'id': 'new', 'sha256': 'source-hash'}]}}
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {'run_id': 'saved-run', 'record': prior}
    return connection, run, record


def test_exact_source_uses_previously_verified_accounting_before_native_comparison():
    connection, run, record = inputs()
    reuse_verified_source(connection, run, record)
    assert record['voucher']['lines'][0]['ledger_guid'] == 'verified'
    assert record['source_file_id'] == 'new' and record['operation'] == 'append'
    assert record['verified_source_reused_from'] == 'saved-run'
    assert record.get('status') != 'duplicate'  # Native verification is still mandatory.
    args = connection.execute.call_args.args[1]
    assert set(args) >= {'tenant', 'actor', 'pc', 'company', 'source-hash'}


@pytest.mark.parametrize('change', [{'operation': 'update'}, {'exception_codes': ['source_values_conflict']},
                                  {'findings': ['Source evidence is uncertain']}])
def test_explicit_corrections_and_uncertain_sources_keep_their_proposal(change):
    connection, run, record = inputs()
    record.update(change)
    reuse_verified_source(connection, run, record)
    connection.execute.assert_not_called()
    assert record['voucher']['lines'][0]['ledger_guid'] == 'new-guess'


def test_changed_document_values_do_not_reuse_the_previous_source_proposal():
    connection, run, record = inputs()
    connection.execute.return_value.fetchone.return_value['record']['document']['total'] = 119
    reuse_verified_source(connection, run, record)
    assert record['voucher']['lines'][0]['ledger_guid'] == 'new-guess'
