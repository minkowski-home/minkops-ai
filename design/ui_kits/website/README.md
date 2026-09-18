# Marketing Site — UI kit

A recreation of minkops.com (`apps/corporate-website/frontend` in the
`minkops-ai` repo), rebuilt on this design system. Five routes, one of which
carries the product's most important interaction: the four-step qualification
funnel.

## Files

| File | What it is | Source |
| --- | --- | --- |
| `SiteChrome.jsx` | Sticky nav, graphite footer, `Section` scaffold | `components/{SiteNav,SiteFooter,PageShell}.tsx` |
| `Landing.jsx` | Hero + 11-agent roster grid | `MinkopsLanding.tsx`, `AgentRosterCard.tsx`, `agentDirectory.ts` |
| `Funnel.jsx` | Four questions → recommended agent stack + hours recovered | `components/QuestionnaireFunnel.tsx` (questions, agent map and maths copied verbatim) |
| `AccessSection.jsx` | Waitlist form + value props | `components/InterestForm.tsx` |
| `Orchestration.jsx` | Three agent-handoff flowcharts | `OrchestrationPage.tsx` |
| `EditorialPages.jsx` | About, Blog, Careers | `AboutPage.tsx`, `BlogsPage.tsx`, `CareersPage.tsx`, `Claude outputs/minkops_linkedin_posts.md` |

## Interactions that work

Nav between all five routes · run the funnel end to end (multi-select on step 2,
live hours-recovered bar, primary + supporting agent recommendations, start
over) · submit the waitlist form to its received state.

## Notes

- Agent status labels ("Live", "Next", "In build") are honest to the repo: only
  Imel and Kall are validated end-to-end. Do not upgrade them in mocks.
- About/Blog/Careers copy in the source is thin; headlines and excerpts here are
  drawn from the LinkedIn drafts in the repo rather than invented claims. No
  pricing, no named customers — Minkops is pre-sale.
- The original site's animated gradient orbs, glass panels and framer-motion
  entrances are intentionally gone; this system is flat and hairline-ruled.
