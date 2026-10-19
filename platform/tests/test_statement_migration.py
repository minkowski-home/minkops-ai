"""The classification-setting retirement preserves unrelated operator settings."""
import os
import unittest
import test_workflow_registration as registration
from psycopg.types.json import Jsonb
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.workflows import load_definition, register_workflow


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'),'TEST_DATABASE_URL is required')
class StatementMigrationTests(unittest.TestCase):
    setUp=registration.WorkflowRegistrationTests.setUp
    remove_schema=registration.WorkflowRegistrationTests.remove_schema

    def test_retired_settings_migrate_idempotently_and_bill_settings_are_unchanged(self):
        bill=register_workflow(self.connection,self.tenant,self.definition)
        definition=load_definition(REPOSITORY_ROOT/'employees/accounts-desk/workflows/statement-entry')
        statement=register_workflow(self.connection,self.tenant,definition)
        legacy={**definition.metadata['tenant_defaults'],'other_side_ledger':'Old fallback','counter_mode':'single','review_mode':'only_exceptions','opening_balance':'123.45'}
        schema={**definition.tenant_schema,'properties':{**definition.tenant_schema['properties'],
            'other_side_ledger':{'type':'string'},'counter_mode':{'enum':['single']}},
            'required':[*definition.tenant_schema['required'],'other_side_ledger','counter_mode']}
        self.connection.execute('UPDATE workflows SET config_values=%s,config_schema=%s WHERE id=%s',(Jsonb(legacy),Jsonb(schema),statement))
        before=self.connection.execute('SELECT config_values,config_schema,config_version FROM workflows WHERE id=%s',(bill,)).fetchone()
        sql=(REPOSITORY_ROOT/'db/migrations/0010_statement_ai_settings.sql').read_text()
        self.connection.execute(sql)
        register_workflow(self.connection,self.tenant,definition)
        values,version=self.connection.execute('SELECT config_values,config_version FROM workflows WHERE id=%s',(statement,)).fetchone()
        self.assertEqual(values,{'review_mode':'only_exceptions','date_format':'dmy','opening_balance':'123.45'})
        self.connection.execute(sql)
        self.assertEqual(self.connection.execute('SELECT config_version FROM workflows WHERE id=%s',(statement,)).fetchone()[0],version)
        self.assertEqual(self.connection.execute('SELECT config_values,config_schema,config_version FROM workflows WHERE id=%s',(bill,)).fetchone(),before)
