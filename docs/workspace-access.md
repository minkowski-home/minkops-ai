# Workspace access

Who belongs to a workspace, what each person can do there, and how people join,
sign in and leave. The rules live in the platform (`minkops_platform/members.py`
and `identity.py`); the API and console only carry them.

## Workspaces and roles

A workspace is one client, such as PR Infra, and a person belongs to exactly one
workspace.

- **Admins** manage the workspace's people and its AI employees. They run every
  workflow, answer every practice question, authorise companies, and change memory
  and rules.
- **Members** run the workflows an admin assigns them, and read the desk's memory.

A workspace always keeps an admin: its last admin cannot be made a member, or
removed, until someone else is an admin.

## Joining

There is no public sign-up.

1. We create each client's workspace and invite its first admin. The operator
   command prints a sign-up link that we send them ([cut-over](rebuild/cutover.md#5-fresh-workspaces)).
2. Admins invite everyone else under **Access**, as admins or members.

An invitation's link works once, for seven days. Resending replaces the link, and
withdrawing the invitation stops it. The link opens a page naming the workspace,
the address and the role.

- **A new person** chooses a name and password, and is signed in. The link reached
  their inbox, so the address is verified.
- **An address that already has an account** signs in first, then accepts.
- **Someone who belongs to another workspace** cannot be invited.

## Workflow assignments

An admin assigns each member the workflows they run, such as Bill entry and
Statement entry. A member launches, sees and decides only those workflows' runs,
tasks and attention items. Another workflow's work is hidden, as if it did not
exist.

Memory, rules and practice belong to the whole Accounts desk, whoever runs which
workflow:

- What a member's approvals teach serves every workflow, and only admins change
  memory or rules.
- A practice question changes one workflow's entries, so it reaches admins and the
  members who run that workflow. Bank payments serves Statement entry; every other
  question serves Bill entry (`accounts/practice.py`, `SERVES`).
- Work that belongs to no workflow, such as a PC's refresh or a company found on a
  PC, reaches everyone.

New members start with no workflows. Members from before assignments existed kept
every workflow they could run (migration 0040).

## Removing someone

When an admin removes someone:

- Their membership, workflow assignments and client access go.
- Their sessions end.
- Their PCs are disconnected, exactly as their own disconnect would: saves a PC had
  begun hold as interrupted, and a client's books continue on a replacing PC
  ([Replacing a PC](accounts-desk.md#replacing-a-pc)).
- Runs they started carry on, for others to decide.

Their account remains, without a workspace, so another workspace may invite them
later.

## Profile and sessions

Everyone's profile, under their name in the sidebar, shows:

- their name, which they may change;
- their password, which changes only with the current one, and signs out every
  other session;
- their sessions: each browser and when it was last used, with sign out for one or
  for all the others;
- their workspace and role.

**Forgot password.** A reset link goes by email and works once, within the hour.
At most three go out in an hour. The answer is the same whether or not an account
uses the address. Using the link signs out every session, and verifies the address.

## What access never changes

Runs, syncs, saves, standing approval and memory never read roles or assignments.
Changing who sees a piece of work never stops it.

A PC's companion authenticates with its own device token, so signing someone out
never stops their PC. Only disconnecting it does.
