"""Progress describes the active parent after preparatory stages finish."""
from unittest.mock import Mock

from minkops_platform.runtime.status import execution_status


def test_statement_classification_remains_visible_after_layout_finishes():
    parent = {'id': 'parent', 'state': 'executing', 'execution_stage': None,
              'awaited_profile_id': None, 'awaited_layout_run_id': None,
              'layout_profiles': [], 'updated_at': 'now'}
    layout = {**parent, 'id': 'layout', 'state': 'review', 'execution_stage': 'layout'}
    connection = Mock()
    connection.execute.side_effect = [Mock(fetchall=lambda: [parent, layout]),
                                      Mock(fetchall=lambda: []), Mock(fetchone=lambda: {'at': None})]
    result = execution_status(connection, {**parent, 'tenant_id': 'tenant', 'task_id': 'task',
                                            'config': {}, 'file_ids': ['statement']})
    assert result['execution']['stage'] == 'reading'
    assert result['execution']['active'] == 1
    assert result['execution']['total'] == 1
