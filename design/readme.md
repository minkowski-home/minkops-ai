# Minkops design system

`design/` is the visual source for the shared Minkops app. The current console lets a signed-in member see Employees, their Workflows, and task Activity. Tenant admins and Minkops operators may edit employee and workflow settings; other members can view them. The mock tenant carries a test Image to Excel workflow. A new PR Infra tenant begins with no employees or workflows.

The app implements four selectable themes: **Minkops Light**, **Minkops Dark**, **Slate Light**, and **Slate Dark**. They all use the locked brand colors and the same components. The orange and slate logo variants supplied with the brand kit are preserved in `assets/logos/`.

## Brand foundation

- **Wordmark:** lowercase `minkops`, Readex Pro at 700 weight with `-0.05em` tracking. The supplied square logos show the orange and slate treatments. In the compact app header, the wordmark remains typeset so it fits the navigation; the theme changes its color.
- **Locked colors:** Ember `#e95d2c`, Rust `#a63e1b`, Slate `#94a3b8`, Graphite `#424048`. `tokens/colors.css` defines them once. `tokens/themes.css` maps semantic roles for each theme.
- **Type:** Readex Pro for headings and names, Libre Franklin for UI and body, IBM Plex Mono for machine output, identifiers, timestamps, and uppercase eyebrow labels.
- **Shape:** flat surfaces, 1px rules, near-square corners, and restrained shadows for overlays only. No glass effects, decorative gradients, or floating cards.
- **Motion:** short color and opacity transitions, with reduced motion respected. Status and progress must remain understandable without animation.
- **Icons:** use `assets/icons/ui/` and `assets/icons/agents/`; extend their 24px outline motif when an icon is genuinely needed. Do not use emoji or Unicode symbols as icons.

Ember marks live signals and focus in the Minkops variants; Rust carries action text and primary controls on light surfaces. Slate and Graphite take those roles in the Slate variants. Semantic tokens handle contrast changes for dark surfaces. Avoid hardcoded orange in a shared component: use `--text-accent`, `--border-accent`, `--surface-selected`, `--signal-live`, and the action tokens instead.

## Console behavior and copy

- The sidebar routes to **Dashboard**, **Employees**, **Workflows**, and **Access**. There is no Agent Teams concept.
- **Employees** lists active employees with their active workflows. Each employee has a detail page with a small, declarative set of controls. Keep controls specific to that employee and understandable without prompt writing.
- **Workflows** lists active, paused, and planned work. It can group by employee or status and sort by name or status. Each workflow detail page shows only the controls that workflow needs.
- **Dashboard** greets the signed-in person by name. Its right Activity pane is resizable and holds active tasks, items needing attention, handoffs, and recent outcomes. Activity items open task detail pages with visible progress and a short account of what is happening.
- The shared app supports real sign-in, sign-up, and tenant membership. **Access** handles invitations and approval. A work email domain can suggest a tenant, but does not grant membership by itself; personal email addresses can be linked too.
- Keep empty states and loading states honest. Do not imply that planned workflows run, that a preview saves to the server, or that an agentic orchestration flow already exists.

Use sentence case for headings, nav, controls, and descriptions. Prefer short, specific labels such as “Needs attention,” “Paused,” and “Save settings.” Avoid invented metrics and generic claims of autonomy. Status uses words as well as color.

## Layout and themes

The shared app uses a 216px sidebar (56px collapsed), a 52px header, and independently scrolling content. The dashboard Activity pane starts at 340px and can be resized from 260px to 500px. On narrow screens it stacks below the main content. The old agent pane and task composer are retired from the current console.

The theme selection is a personal preference stored by the browser. Each option changes the entire app, including sign-in, chrome, forms, settings, and task progress. Slate Light uses the pale slate background from the supplied slate logo; Slate Dark uses the same Slate accents against the existing dark ramp. Minkops Light remains the original light direction.

`styles.css` loads shared tokens and element defaults. `console.css` and `login.css` are the actual shared app styles, imported by `apps/solution-web`. The static preview at `ui_kits/console/index.html` uses these same files and local sample data to illustrate the screens and interactions. The connected app owns authentication, persistence, and workflow execution.

## Files and scope

| Path | Purpose |
| --- | --- |
| `tokens/colors.css`, `tokens/themes.css` | Brand palette, semantic roles, four theme maps |
| `tokens/typography.css`, `tokens/fonts.css` | Type roles and font loading |
| `tokens/spacing.css`, `tokens/surfaces.css`, `tokens/motion.css`, `tokens/layout.css`, `tokens/base.css` | Shared foundations |
| `styles.css`, `console.css`, `login.css` | App style entry points |
| `assets/logos/` | Supplied orange and slate artwork |
| `assets/icons/` | Existing product icons |
| `guidelines/` | Brand and theme specimens |
| `ui_kits/console/` | Current shared-console static preview |
| `ui_kits/website/`, `components/product/` | Historical marketing and agent-console specimens; they are not the current console contract |

The warehouse has no UI contract in this migration. The client-specific apps do not define these shared screens or theme rules.
