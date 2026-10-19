/* global window, document */
import {test,expect} from '@playwright/test';

async function setup(page,context,{native=null,canRestart=true,version='development'}={}) {
  await page.clock.install();
  await page.addInitScript(({native,canRestart})=>{
    window.updateQA={native,restarts:0};
    window.minkopsDesktop={version:1,status:async()=>({version:'0.8.1',update:window.updateQA.native}),
      checkUpdates:async()=>{window.updateQA.native={state:'ready',version:'0.8.2'};},
      ...(canRestart?{restartForUpdate:async()=>{window.updateQA.restarts++;return true;}}:{})};
  },{native,canRestart});
  await context.route('**/version.json',r=>r.fulfill({json:{id:version}}));
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/,r=>r.fulfill({body:'',contentType:'text/css'}));
  await context.route('**/api/**',r=>{
    const auth=r.request().url().endsWith('/auth/session');
    return r.fulfill({json:auth?{id:'qa',name:'QA',email:'qa@example.com',memberships:[{slug:'mock-tenant',role:'admin'}],csrf_token:'csrf'}
      :{tenant:{slug:'mock-tenant',name:'QA'},can_edit:true,attention_count:0,employees:[],workflows:[],tasks:[]}});
  });
  await page.goto('http://127.0.0.1:3000/mock-tenant/dashboard');
  await expect(page.getByRole('heading',{name:"Let's start the day, QA."})).toBeVisible();
}

test('new frontend and native download banners stay usable on mobile; restart is explicit',async({page,context},testInfo)=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await setup(page,context,{native:{state:'downloading',version:'0.8.2'},version:'next-build'});
  await expect(page.getByText('Downloading Minkops 0.8.2… You can keep working.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Refresh for latest version'})).toBeVisible();
  await page.evaluate(()=>{window.updateQA.native={state:'ready',version:'0.8.2'};});
  await page.clock.fastForward(31_000);
  await expect(page.getByRole('button',{name:'Restart when safe'})).toBeVisible();
  await page.screenshot({path:testInfo.outputPath('updates-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('updates-mobile.png')});
  await page.getByRole('button',{name:'Restart when safe'}).click();
  await expect(page.getByText(/Restart scheduled/)).toBeVisible();
  expect(await page.evaluate(()=>window.updateQA.restarts)).toBe(1);
  expect(errors).toEqual([]);
});

test('current builds stay quiet and older companions explain automatic installation',async({page,context})=>{
  await setup(page,context,{native:{state:'ready',version:'0.8.1'},canRestart:false});
  await expect(page.getByText('The update installs when Minkops is idle or quits.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Restart when safe'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Refresh for latest version'})).toHaveCount(0);
});

test('update errors can retry and frontend refresh happens only on an explicit click',async({page,context})=>{
  await setup(page,context,{native:{state:'error'},version:'next-build'});
  await expect(page.getByText(/App updates could not be checked/)).toBeVisible();
  const firstLoad=await page.evaluate(()=>window.performance.timeOrigin);
  await page.getByRole('button',{name:'Retry update check'}).click();
  await page.clock.fastForward(31_000);
  await expect(page.getByRole('button',{name:'Restart when safe'})).toBeVisible();
  expect(await page.evaluate(()=>window.performance.timeOrigin)).toBe(firstLoad);
  await page.getByRole('button',{name:'Refresh for latest version'}).click();
  await expect.poll(()=>page.evaluate(()=>window.performance.timeOrigin)).not.toBe(firstLoad);
});
