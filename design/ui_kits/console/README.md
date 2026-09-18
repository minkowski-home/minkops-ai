# Operator Console — UI kit

A recreation of the Minkops client app (`apps/client-app/web` in the `minkops-ai`
repo), rebuilt on this design system. The console is where a tenant's operator
watches their fleet, hands work to agents, and clears the human-interrupt queue.

## Screens

| File | What it is | Source |
| --- | --- | --- |
| `LoginScreen.jsx` | Split sign-in: graphite story panel + form | `src/pages/Login.tsx` |
| `ConsoleShell.jsx` | Sidebar (collapsible), header, pane headers | `src/components/layout/{Sidebar,AppShell}.tsx` |
| `AgentsPane.jsx` | Left pane — teams and individual agents with switches | `src/components/agents/AgentPanel.tsx` |
| `TaskThread.jsx` | Centre pane — task chat + composer | `src/components/task/TaskPanel.tsx` |
| `AttentionQueue.jsx` | Right pane — interrupts by priority | `src/components/interrupt/InterruptPanel.tsx` |
| `AgentsScreen.jsx` | `/agents` — hire-an-agent catalogue | `README.md` planned-agents roster |
| `PlaceholderScreen.jsx` | `/analytics`, `/settings` — routed but undesigned | — |
| `ConsoleData.jsx` | Mock agents, messages, interrupts, user | `src/mock/*.ts` |

## Interactions that work

Sign in → dashboard · collapse the sidebar · switch agents and the whole team
on/off · select an agent row · type a task (Enter sends; an agent replies after
a beat) · resolve / acknowledge / dismiss interrupts, with the header badge and
priority pills recounting live · navigate to the agent catalogue.

## Deliberately absent

`/analytics` and `/settings` are real routes in the codebase with no screens
shipped. They render an explicit "not designed yet" state rather than an
invented dashboard. The original app also shipped a three-theme selector
(light / dark / paper); this system replaces that with a single light theme, so
the control is gone.
