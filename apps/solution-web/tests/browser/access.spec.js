/* global URL, document, window */
import {test, expect} from '@playwright/test';

const APP = 'http://127.0.0.1:3000';
const flows = [{id:'w-bills', key:'bill-entry', name:'Bill entry', employee_ids:[]},
  {id:'w-statements', key:'statement-entry', name:'Statement entry', employee_ids:[]}];

/** A mocked API whose people, invitations and sessions change as the page acts; returns the calls it saw. */
async function mocked(context, {signedIn = true, invitation = null} = {}) {
  const calls = [];
  let user = signedIn ? {id:'u-admin', name:'Asha Rao', email:'asha@example.com', is_platform_admin:false,
    memberships:[{slug:'mock-tenant', name:'PR Infra', role:'admin'}], csrf_token:'csrf'} : null;
  let members = [
    {id:'u-admin', name:'Asha Rao', email:'asha@example.com', role:'admin', joined_at:'2026-10-01T00:00:00Z', workflow_ids:[], pcs:1},
    {id:'u-ravi', name:'Ravi Kumar', email:'ravi@example.com', role:'member', joined_at:'2026-10-02T00:00:00Z',
      workflow_ids:['w-bills'], pcs:2}];
  let invitations = [{id:'i-1', email:'neha@example.com', role:'member', created_at:'2026-10-20T00:00:00Z',
    expires_at:'2026-10-27T00:00:00Z', expired:false, invited_by:'Asha Rao'}];
  let sessions = [
    {id:'s-here', user_agent:'Firefox on Windows', created_at:'2026-10-20T09:00:00Z', last_seen_at:'2026-10-23T09:00:00Z', current:true},
    {id:'s-phone', user_agent:'Chrome on Android', created_at:'2026-10-19T09:00:00Z', last_seen_at:'2026-10-22T09:00:00Z', current:false},
    {id:'s-laptop', user_agent:'Edge on Windows', created_at:'2026-10-18T09:00:00Z', last_seen_at:'2026-10-21T09:00:00Z', current:false}];
  await context.route(/https:\/\/(fonts.googleapis.com|fonts.gstatic.com)/, route => route.fulfill({body:'', contentType:'text/css'}));
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    const body = request.postData() ? request.postDataJSON() : null;
    if (method !== 'GET') calls.push([method, path, body]);
    const reply = (json, status = 200) => route.fulfill({status, json});
    if (path === '/api/auth/session') return reply(user);
    if (path === '/api/auth/me' && method === 'PATCH') { user = {...user, name:body.name}; return reply(user); }
    if (path === '/api/auth/sessions') return reply(sessions);
    if (path.startsWith('/api/auth/sessions/') && method === 'DELETE') {
      sessions = sessions.filter(s => s.id !== path.split('/').at(-1)); return reply({message:'Signed out there.'});
    }
    if (path === '/api/auth/sessions/end-others') { sessions = sessions.filter(s => s.current); return reply({message:'Signed out of 1 other session.', ended:1}); }
    if (path === '/api/auth/password') {
      return body.current_password === 'right password!!' ? reply({message:'Password changed. Your other sessions are signed out.'})
        : reply({detail:'The current password is not right.'}, 422);
    }
    if (path === '/api/auth/password-reset') return reply({message:'If an account uses this email, a link to reset its password is on its way.'}, 202);
    if (path === '/api/auth/password-reset/confirm') return reply({message:'Password changed. Sign in with your new password.'});
    if (path.startsWith('/api/auth/invitations/') && path.endsWith('/accept')) {
      user = {id:'u-new', name:body.name, email:invitation.email, is_platform_admin:false,
        memberships:[{slug:'mock-tenant', name:'PR Infra', role:'member'}], csrf_token:'csrf'};
      return reply({message:'Workspace joined.', workspace:'mock-tenant'});
    }
    if (path.startsWith('/api/auth/invitations/')) return invitation ? reply(invitation) : reply({detail:'This invitation link is invalid, used or expired. Ask your workspace admin for a new one.'}, 404);
    if (path.endsWith('/workspace')) return reply({tenant:{slug:'mock-tenant', name:'PR Infra'}, can_edit:true, employees:[], workflows:flows, tasks:[], attention_count:0});
    if (path.endsWith('/members') && method === 'GET') return reply(members);
    if (path.includes('/members/') && method === 'PATCH') {
      const id = path.split('/').at(-1);
      members = members.map(m => m.id === id ? {...m, ...(body.role ? {role:body.role} : {}),
        ...(body.workflow_ids ? {workflow_ids:body.workflow_ids} : {})} : m);
      return reply(members.find(m => m.id === id));
    }
    if (path.includes('/members/') && method === 'DELETE') {
      const gone = members.find(m => m.id === path.split('/').at(-1));
      members = members.filter(m => m !== gone); return reply({pcs:gone.pcs});
    }
    if (path.endsWith('/invitations') && method === 'GET') return reply(invitations);
    if (path.endsWith('/invitations') && method === 'POST') {
      invitations = [{id:'i-2', email:body.email, role:body.role, created_at:'2026-10-23T00:00:00Z', expires_at:'2026-10-30T00:00:00Z',
        expired:false, invited_by:'Asha Rao'}, ...invitations];
      return reply({message:`Invitation sent to ${body.email}.`, invitation:invitations[0]}, 201);
    }
    if (path.endsWith('/resend')) return reply({message:'Invitation sent to neha@example.com.'});
    if (path.includes('/invitations/') && method === 'DELETE') {
      invitations = invitations.filter(i => i.id !== path.split('/').at(-1)); return reply({message:'Invitation withdrawn.'});
    }
    if (path.endsWith('/attention')) return reply([]);
    return reply([]);
  });
  return calls;
}

test('signing in offers a reset, and a reset link sets a new password', async ({page, context}) => {
  const calls = await mocked(context, {signedIn:false});
  await page.goto(`${APP}/login`);
  await expect(page.getByRole('link', {name:'Create an account'})).toHaveCount(0);
  await page.getByRole('link', {name:'Forgot your password?'}).click();
  await page.getByRole('textbox', {name:'Email'}).fill('asha@example.com');
  await page.getByRole('button', {name:'Email me a link'}).click();
  await expect(page.getByRole('status')).toContainText('If an account uses this email');
  await page.goto(`${APP}/reset/token-1`);
  await page.getByLabel('New password', {exact:true}).fill('a brand new password');
  await page.getByLabel('New password again').fill('a different password');
  await page.getByRole('button', {name:'Change password'}).click();
  await expect(page.getByRole('alert')).toContainText('The passwords differ');
  await page.getByLabel('New password again').fill('a brand new password');
  await page.getByRole('button', {name:'Change password'}).click();
  await expect(page.getByRole('status')).toContainText('Password changed');
  expect(calls).toEqual([
    ['POST', '/api/auth/password-reset', {email:'asha@example.com'}],
    ['POST', '/api/auth/password-reset/confirm', {token:'token-1', password:'a brand new password'}],
  ]);
});

test('an invitation creates the account and opens the workspace; an existing account signs in first', async ({page, context}) => {
  const invitation = {workspace:'PR Infra', email:'neha@example.com', role:'member', expires_at:'2026-10-30T00:00:00Z', account:false};
  const calls = await mocked(context, {signedIn:false, invitation});
  await page.goto(`${APP}/invite/token-2`);
  await expect(page.getByText('You are invited to PR Infra as a member.')).toBeVisible();
  await expect(page.getByRole('textbox', {name:'Email'})).toHaveValue('neha@example.com');
  await page.getByRole('textbox', {name:'Your name'}).fill('Neha Shah');
  await page.getByLabel('Password', {exact:true}).fill('a long enough password');
  await page.getByLabel('Password again').fill('a long enough password');
  await page.getByRole('button', {name:'Create account and join PR Infra'}).click();
  await expect(page).toHaveURL(/\/mock-tenant\/dashboard$/);
  expect(calls).toEqual([['POST', '/api/auth/invitations/token-2/accept', {name:'Neha Shah', password:'a long enough password'}]]);
  invitation.account = true;
  const fresh = await page.context().browser().newContext();
  await mocked(fresh, {signedIn:false, invitation});
  const other = await fresh.newPage();
  await other.goto(`${APP}/invite/token-3`);
  await expect(other.getByRole('link', {name:'Sign in to continue'})).toHaveAttribute('href', '/login?next=%2Finvite%2Ftoken-3');
  await fresh.close();
});

test('a profile renames, changes the password and signs out other sessions', async ({page, context}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const calls = await mocked(context);
  await page.goto(`${APP}/mock-tenant/dashboard`);
  await page.getByRole('link', {name:'Your account'}).click();
  await expect(page).toHaveURL(/\/mock-tenant\/profile$/);
  await expect(page.getByRole('region', {name:'Workspace'})).toContainText('PR Infra · Admin');
  await page.getByRole('textbox', {name:'Name'}).fill('Asha R.');
  await page.getByRole('button', {name:'Save name'}).click();
  await expect(page.getByRole('status')).toContainText('Name saved.');
  await page.getByLabel('Current password').fill('wrong password!!');
  await page.getByLabel('New password', {exact:true}).fill('a new long password');
  await page.getByLabel('New password again').fill('a new long password');
  await page.getByRole('button', {name:'Change password'}).click();
  await expect(page.getByRole('status')).toContainText('The current password is not right.');
  await page.getByLabel('Current password').fill('right password!!');
  await page.getByRole('button', {name:'Change password'}).click();
  await expect(page.getByRole('status')).toContainText('Your other sessions are signed out.');
  const sessions = page.getByRole('region', {name:'Sessions'});
  await expect(sessions.locator('article').first()).toContainText('This browser');
  await sessions.locator('article').filter({hasText:'Chrome on Android'}).getByRole('button', {name:'Sign out there'}).click();
  await expect(sessions.locator('article')).toHaveCount(2);
  await sessions.getByRole('button', {name:'Sign out of every other session'}).click();
  await expect(sessions.locator('article')).toHaveCount(1);
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('profile.png'), fullPage:true});
  expect(calls).toEqual([
    ['PATCH', '/api/auth/me', {name:'Asha R.'}],
    ['POST', '/api/auth/password', {current_password:'wrong password!!', new_password:'a new long password'}],
    ['POST', '/api/auth/password', {current_password:'right password!!', new_password:'a new long password'}],
    ['DELETE', '/api/auth/sessions/s-phone', null],
    ['POST', '/api/auth/sessions/end-others', null],
  ]);
  expect(errors).toEqual([]);
});

test('admins assign workflows, change roles, remove people and invite', async ({page, context}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const calls = await mocked(context);
  await page.goto(`${APP}/mock-tenant/access`);
  const asha = page.locator('article').filter({hasText:'asha@example.com'});
  const ravi = page.locator('article').filter({hasText:'ravi@example.com'});
  await expect(asha).toContainText('Runs every workflow · 1 connected PC');
  await expect(ravi.getByRole('checkbox', {name:'Bill entry'})).toBeChecked();
  await ravi.getByRole('checkbox', {name:'Statement entry'}).check();
  await expect(ravi.getByRole('checkbox', {name:'Statement entry'})).toBeChecked();
  await ravi.getByRole('combobox', {name:'Role of Ravi Kumar'}).selectOption('admin');
  await expect(page.getByRole('status')).toContainText('Ravi Kumar is now admin.');
  await expect(ravi).toContainText('Runs every workflow');
  await ravi.getByRole('button', {name:'Remove'}).click();
  await expect(page.getByRole('alertdialog', {name:'Remove Ravi Kumar'}))
    .toContainText('their 2 connected PCs are disconnected');
  await page.getByRole('button', {name:'Remove Ravi Kumar'}).click();
  await expect(page.getByRole('status')).toContainText('Ravi Kumar was removed.');
  await expect(page.locator('article').filter({hasText:'ravi@example.com'})).toHaveCount(0);
  const neha = page.locator('article').filter({hasText:'neha@example.com'});
  await expect(neha).toContainText('invited by Asha Rao');
  await neha.getByRole('button', {name:'Resend'}).click();
  await expect(page.getByRole('status')).toContainText('Invitation sent to neha@example.com.');
  await neha.getByRole('button', {name:'Withdraw'}).click();
  await expect(page.getByRole('status')).toContainText('Invitation withdrawn.');
  await page.getByRole('textbox', {name:'Email'}).fill('kiran@example.com');
  await page.getByRole('combobox', {name:'Invite as'}).selectOption('admin');
  await page.getByRole('button', {name:'Send invitation'}).click();
  await expect(page.locator('article').filter({hasText:'kiran@example.com'})).toContainText('Admin');
  for (const theme of ['minkops-light', 'minkops-dark']) {
    await page.getByRole('combobox', {name:'Theme', exact:true}).selectOption(theme);
    await page.screenshot({path:testInfo.outputPath(`access-${theme}.png`), fullPage:true});
  }
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(calls).toEqual([
    ['PATCH', '/api/tenants/mock-tenant/members/u-ravi', {workflow_ids:['w-bills', 'w-statements']}],
    ['PATCH', '/api/tenants/mock-tenant/members/u-ravi', {role:'admin'}],
    ['DELETE', '/api/tenants/mock-tenant/members/u-ravi', null],
    ['POST', '/api/tenants/mock-tenant/invitations/i-1/resend', null],
    ['DELETE', '/api/tenants/mock-tenant/invitations/i-1', null],
    ['POST', '/api/tenants/mock-tenant/invitations', {email:'kiran@example.com', role:'admin'}],
  ]);
  expect(errors).toEqual([]);
});
