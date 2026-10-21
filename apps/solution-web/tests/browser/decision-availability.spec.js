/* global URL */
import {test, expect} from '@playwright/test';

test('a compact bill result explains a blocked supplier action without offering it', async ({page,context}) => {
  const reason='The supplier jurisdiction conflicts with the company state. Review it in Tally.';
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,route=>route.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;let body;
    if(path==='/api/auth/session')body={id:'user',name:'QA',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'};
    else if(path.endsWith('/workspace'))body={tenant:{slug:'mock-tenant',name:'QA'},can_edit:true,employees:[],tasks:[],workflows:[{id:'bill',key:'bill-entry',presentation:'accounts-bill'}]};
    else if(path.endsWith('/accounts/tasks/task/run'))body={id:'run',actor_id:'user',task_id:'task',workflow_key:'bill-entry',state:'review',writes:[],config:{file_provenance:[{id:'new',path:'new-supplier.pdf'}]},
      result:{records:[{source_file_id:'new',data:{invoice_number:'NEW-1',total:8850},voucher:{party:{new_supplier:true}},exception_codes:['supplier_missing'],findings:['Supplier missing'],evidence:[],allowed_actions:['nothing'],
        unavailable_actions:{supplier:{code:'decision_unavailable',message:reason}},preview:{company:'Pradeepraj Infra',voucher_type:'Purchase',date:'2026-09-02',number:'NEW-1',party:'New supplier',total:8850,lines:[]}}],findings:[]}};
    else if(path.endsWith('/tasks/task'))body={id:'task',workflow_id:'bill',title:'Bill entry',status:'attention',events:[]};
    else throw Error(path);
    await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/tasks/task');
  await expect(page.getByText(`Cannot create this ledger: ${reason}`,{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Create this ledger',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Show details',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('Pradeepraj Infra');
});
