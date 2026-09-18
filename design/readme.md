# Minkops Design System

Minkops (minkops.com) sells **AI employees**: a suite of autonomous agents that
take whole roles — email, support, lead calling, content, analytics, store
operations — rather than single workflow steps. Agents intercommunicate through
a shared knowledge graph, policy model and orchestration layer, and a customer
"hires" whatever set of them they need. A fleet runs continuously, 24×7, and
escalates to a human whenever a decision sits above the agent's authority
threshold. Minkops is a product of Minkowski Home and is pre-sale: only two
agents (Imel, the email handler, and Kall, the support rep) run end to end
today; the other nine are roadmap.

This design system replaces the previous visual direction entirely. Two things
carried over unchanged, at the user's instruction:

1. **The wordmark typeface** — Readex Pro, 700 weight, `-0.05em` tracking, always lowercase.
2. **The four brand colors** — Ember `#e95d2c`, Rust `#a63e1b`, Slate `#94a3b8`, Graphite `#424048`.

Everything else — the glassmorphism, the animated gradient orbs, the neon
pink/blue accents, the three-theme system (light/dark/paper), Cormorant
Garamond, Apple SD Gothic Neo — is retired.

## Sources

- **Codebase:** `minkops-ai/` (mounted locally, read-only). Read in full:
  - `docs/brand-guidelines.md` — the previous brand system (superseded by this one).
  - `shared/brand/tokens.css`, `shared/brand/theme.ts` — the previous token set; the four brand colors were lifted from its "Brand accents" block.
  - `apps/corporate-website/frontend/` — the marketing site (React + Vite + framer-motion + react-router).
  - `apps/client-app/web/` — the operator console (React + Vite).
  - `README.md` — product description and the planned-agent roster.
  - `Claude outputs/minkops_linkedin_posts.md` — the most reliable sample of the brand's written voice.
- **Not used:** `minkops-ai/design/` — a separate warm-paper/Fraunces exploration the user asked to ignore.
- No Figma file, slide template, or logo artwork was provided.

## Products

| Surface | Where it lives | Recreated in |
| --- | --- | --- |
| Marketing site | `apps/corporate-website` (Vercel, minkops.com) | `ui_kits/website/` |
| Operator console | `apps/client-app/web` | `ui_kits/console/` |

Both are recreations of the shipped code, not redesigns of the product's
information architecture.

---

## The direction, in one line

**An operations console, not a showroom.** White ground, hairline slate rules,
near-square corners, Readex Pro headlines over Libre Franklin text, and IBM Plex
Mono anywhere a machine produced the value. Ember is a signal, not decoration.

---

## Content fundamentals

**Voice.** Confident and specific; flatly unimpressed by its own category. The
strongest single line in the source material is the product thesis: *"hire an AI
employee the way you'd hire a person — for a specific role, with real
responsibility — except it starts on day one, works nights and weekends, and
never asks for a raise."* Write like that: a claim, then the concrete thing that
makes it true.

**Person.** First person plural for the company (*"We've gone the opposite
way"*, *"we build the AI employees we're selling before we sell them"*). Second
person for the customer, and never as flattery — *"Where does your week actually
disappear?"*, *"Be honest — this is where your ROI calculation starts."* In the
console, agents speak in first person about their own work (*"I've received your
task and I'm working on it"*).

**Casing.** Sentence case everywhere: headings, buttons, labels, nav. Two
exceptions: the wordmark is always lowercase (`minkops`), and mono eyebrows are
uppercase with 0.14em tracking (`STEP 02 / TIME AUDIT`, `NEEDS ATTENTION (3)`).
Agent names are capitalised proper nouns — Imel, Kall, Leed, Ora, Eko, Floc,
Insi, Kim, Cruz, Hosi, Prex.

**Length and rhythm.** Headlines under eight words. Body paragraphs two to four
sentences, one idea each. Console strings are as short as they can be while
staying unambiguous: *"All clear"*, *"3 agents active"*, *"Enter to send ·
Shift+Enter for new line"*.

**Honesty rules — these are load-bearing.** The source material is disciplined
about not overclaiming, and the design system inherits that: no invented
metrics, no implied paying customers, no pricing, no named prospects. Agent
status must be truthful (Imel and Kall are live; everything else is "next" or
"in build"). Estimates are stated as ranges with their basis shown (*"8–12 hrs /
wk"*, *"up to 68% automated"*, *"a conservative estimate"*). Worst case is named
out loud: *"Worst case, it tells you Minkops isn't the right fit yet."*

**Naming.** *Agents* or *AI employees*, never "bots" or "assistants". *Operator*
for the human in the console. *Interrupt* for a queued item needing a human;
the pane is titled *"Needs attention"*. *Fleet* for a tenant's set of agents,
*team* for a named group inside it. *Tenant* for the customer org.

**What we don't do.** No emoji, anywhere — not in product, not in marketing, not
in commit-adjacent copy. No exclamation marks. No "revolutionary", "seamless",
"unlock", "supercharge". No em-dash-heavy AI cadence. No "this, not that"
constructions. No exhortations to imagine ROI — *"Most 'AI for your business'
pitches ask you to imagine the ROI. We'd rather just show you."*

**Error and empty copy** states the fact, then the fix. *"Invalid email or
password. Please try again."* · *"Access is restricted to authorised tenants
only."* · *"No items need your attention right now. Agents are running
smoothly."*

---

## Visual foundations

**Colors.** Four locked brand colors and one Slate-hued neutral ramp
(`--n-0` → `--n-900`). The division of labour matters more than the hexes:

- **Ember `#e95d2c`** is the *signal*. Live status dots, the active nav marker,
  the switch-on track, focus rings, progress fills, the 2px left edge on an item
  awaiting a human. It fails 4.5:1 on white, so it never carries text.
- **Rust `#a63e1b`** is the *action*. Primary button fills, accent text, links,
  active-item labels. 5.4:1 on white.
- **Slate `#94a3b8`** is *structure* — it seeds the whole neutral ramp; borders,
  rules and muted type descend from it.
- **Graphite `#424048`** is the *dark surface* — footer band, sidebar of the
  login screen, agent avatars, human message bubbles, the terminal node in a
  flow diagram.

Statuses are deliberately desaturated (`#1f6f45`, `#8a6212`, `#b3261e`) so they
sit beside Ember without a colour fight. Green never means "active" — only a
finished, good outcome. Max two background tones per view: white plus either
`--surface-sunken` (#f8f9fa) or one graphite band.

**Type.** Three faces, strict roles. Readex Pro (600, `-0.03em`) for the
wordmark, headings and agent names — it is the only voice-carrying face. Libre
Franklin for every piece of running text and UI label, 15px/1.5 base, measure
capped at 68ch. IBM Plex Mono for machine output: ids, timestamps, relative
times, confidence percentages, tenant handles, and the uppercase eyebrow device.
If a value came from a machine, it is mono. Minimum sizes: 12px in the console,
13px for body copy in dense panes, 15px on the marketing site.

**Backgrounds.** Flat. No photography, no illustration, no repeating pattern, no
texture, no grain, no gradient meshes — the one gradient permitted anywhere is
the flat Ember fill of a progress bar. Sections are separated by a 1px hairline,
not by a colour change. The marketing site is white with occasional
`--surface-sunken` bands; the console is white with a sunken sidebar and sunken
attention pane. There is no imagery in the system at all, which is a
consequence of the source: the codebase contains no photography or illustration
either.

**Borders and rules.** This is a hairline-first system: structure comes from 1px
rules, never from shadow. Three weights — `--border-hairline` (#e5e9ed) inside
panels, `--border-default` (#d2d8de) on cards and inputs, `--border-strong`
(#b7c0c9) for hover and indicators. Two 2px edges carry meaning: an Ember **left**
edge means "a human is needed here", an Ember **top** edge marks an agent node
in a flow diagram.

**Corner radii.** Near-square. 2px for badges and small chips, 3px for buttons
and inputs, 4px for cards and panels — 4px is the ceiling for anything
rectangular. Pills (`--radius-pill`) are reserved for priority summaries and
switch tracks; circles for status dots only.

**Cards.** White, 4px radius, 1px `--border-default`, 16px padding, **no
shadow**. Variants: `sunken` (tinted fill, hairline border) for wells and
secondary panes; `inverse` (graphite) for dark bands; `accentEdge` (2px Ember
left edge) strictly for human-action items. Never nest more than two cards, never
stack shadows.

**Shadows.** Two, plus a focus ring. `--shadow-pop` for menus and popovers,
`--shadow-overlay` for dialogs, `--shadow-focus` (white gap + Ember halo) for
keyboard focus. Nothing that doesn't leave the plane gets a shadow. No inner
shadows anywhere.

**Transparency and blur.** None. The previous brand was built on
`backdrop-filter: blur(18px)` glass surfaces; this one has no blur, no
translucent panels, no protection gradients. Where the old system floated a
glass card, this one draws a rule. The only alpha values in the token set are
Ember tints (`0.08` / `0.14` / `0.24`) used as flat fills and a Slate tint for
halos.

**Hover.** Colour only. Backgrounds step one level (`transparent` →
`--surface-sunken`; white → `--n-50`), text darkens toward `--text-primary`,
borders step to `--border-strong`. Interactive cards swap their border to Ember.
No lift, no scale, no shadow bloom — the old system's `scale(1.05)` CTA hover is
explicitly retired.

**Press.** 80ms colour deepening (`--rust-press` `#8a3216`, `--graphite-press`
`#2f2e34`). No shrink, no translate.

**Selection.** An Ember inset edge (`--shadow-inset-active`) plus a 14% Ember
wash — rows never get a solid coloured fill.

**Motion.** Short, flat, and colour-first: 80ms press, 120ms hover, 180ms
toggles and panels, 280ms entrances. Easing `cubic-bezier(0.2, 0, 0, 1)` out,
`cubic-bezier(0.4, 0, 0.2, 1)` in-out. Permitted animations: colour and
background transitions, the switch knob slide, the progress-bar fill, the
three-dot "agent is working" opacity pulse (1.2s), and a 280ms fade-up on first
paint of a pane. Nothing loops, nothing bounces, nothing parallaxes. The
previous site's 8s pulsing orbs and per-section framer-motion entrances are gone.

**Layout.** Fixed chrome: 216px sidebar (56px collapsed), 52px header, 288px
agent pane, 340px attention pane — all tokenised in `tokens/layout.css`. The
console is a full-height flex shell with independently scrolling panes and no
page scroll. The marketing site is a 1200px centred container with 96px/32px
section padding and a sticky 64px nav. Text measure never exceeds 68ch. Console
hit targets are 36px minimum (44px on touch).

---

## Iconography

**One source, copied from the product.** The Minkops codebase ships its own
hand-drawn inline SVG set and no icon-font, sprite, or npm icon package. Both
families were copied out verbatim into `assets/icons/` and are exposed through a
single `<Icon>` component — the one intentional addition to the component
inventory (a wrapper, not a new visual).

- **UI glyphs (13)** — `assets/icons/ui/`: home, agents, tasks, analytics,
  settings, chevron-left, chevron-right, send, bell, check, x, palette, logout.
  24×24 grid, `fill: none`, `stroke: currentColor`, 1.8px stroke (2px for
  chevrons and x, 2.2px for check), round caps and joins. Rendered at 17–18px in
  chrome, 12–15px inside buttons.
- **Agent role glyphs (11)** — `assets/icons/agents/`: designer, social, writer,
  manager, host, kitchen, support, sales, retail, analyst, email. Same 24×24
  grid at 1.65px stroke. Every one is built from the same motif — a head and
  shoulders plus a small role modifier (a chart, an envelope, a chef's hat, an
  arrow). One glyph per agent, always the same pairing; Imel is `email`, Kall is
  `support`, Insi is `analyst`. Rendered at 20–26px, usually in Rust inside a
  bordered inset tile.

Do not substitute Lucide, Heroicons, Material or any other library, and do not
draw new glyphs freehand: if a new agent or action needs a mark, extend the
existing motif at the same stroke weight. Emoji are never used. Unicode
characters are not used as icons; the one typographic exception in the source
(an `↗` before an hours-saved figure) has been dropped in favour of plain text.

**Logo:** none exists. The provided sources contain no logo file, mark, or
favicon artwork beyond a default `favicon.ico`, so **nothing was drawn**. The
brand renders as the type-set lowercase wordmark, optionally preceded by a
7–8px Ember dot (the one permitted companion element, taken from the console
sidebar and login screen). See `guidelines/brand-wordmark-lockup.card.html`.

---

## Fonts

All three faces are Google Fonts, loaded via `tokens/fonts.css`:

- **Readex Pro** — kept from the original brand, unchanged.
- **Libre Franklin** — new. The old system had no real text face; it fell back
  to Apple SD Gothic Neo and the system stack, which cannot be shipped.
- **IBM Plex Mono** — new. Replaces the old `"SF Mono", "Fira Code", …` stack,
  which is also unshippable.

⚠️ **No font binaries exist in the source repo**, so this system loads all three
from the Google Fonts CDN rather than declaring local `@font-face` rules. If you
have licensed files (woff2), drop them in `assets/fonts/` and I'll convert
`tokens/fonts.css` to real `@font-face` declarations.

---

## Components

Twenty-four exports across four groups. The inventory is derived from the two
apps' own components — every family below has a counterpart in the codebase.

**`components/core/`** — Button · IconButton · Icon · Badge · PriorityPill ·
StatusDot · Toggle · Card · Avatar · Eyebrow

**`components/forms/`** — Field · Input · Textarea · Select · OptionRow

**`components/feedback/`** — ProgressSteps · EmptyState · TypingIndicator

**`components/product/`** — AgentRow · InterruptCard · MessageBubble ·
AgentTile · FlowNode (+ FlowArrow)

Each directory holds `<Name>.jsx`, `<Name>.d.ts`, `<Name>.prompt.md` and one
`@dsCard` HTML sheet showing its states.

### Intentional additions

- **`Icon`** — the codebase exports 24 separate icon components; this wraps them
  in one name-keyed component so consumers have a single API and a single stroke
  contract. No new glyphs were invented.
- **`Eyebrow`** — the uppercase mono kicker appears in five different ad-hoc
  implementations across the two apps (`section-kicker`, `funnel-kicker`,
  `agent-section-label`, `interrupt-panel-title`, `task-panel-subtitle`). Promoted
  to one component because it is the brand's signature small-type device.

### Not carried over

`ThemeSelector` — the source app shipped a three-theme picker (light / dark /
paper). This system defines a single light theme, so the control has no purpose.

---

## Index

| Path | What it is |
| --- | --- |
| `styles.css` | The single entry point — `@import`s only. Link this. |
| `tokens/colors.css` | Brand colors, neutral ramp, statuses, semantic aliases |
| `tokens/typography.css` | Faces, weights, size scale, composed type roles |
| `tokens/spacing.css` | 4px scale + padding/gap presets |
| `tokens/surfaces.css` | Radii, border weights, the two shadows, focus ring |
| `tokens/motion.css` | Durations and easings |
| `tokens/layout.css` | Fixed chrome dimensions, measures, hit targets |
| `tokens/base.css` | Element defaults (body, headings, links, focus) |
| `tokens/fonts.css` | Webfont loading |
| `assets/icons/ui/` | 13 UI glyphs (SVG) |
| `assets/icons/agents/` | 11 agent role glyphs (SVG) |
| `components/core/` | Buttons, badges, signals, avatars, surfaces |
| `components/forms/` | Field, Input, Textarea, Select, OptionRow |
| `components/feedback/` | ProgressSteps, EmptyState, TypingIndicator |
| `components/product/` | AgentRow, InterruptCard, MessageBubble, AgentTile, FlowNode |
| `guidelines/*.card.html` | 19 foundation specimen cards (Colors, Type, Spacing, Surfaces, Brand) |
| `ui_kits/console/` | Operator console recreation — see its README |
| `ui_kits/website/` | Marketing site recreation — see its README |
| `thumbnail.html` | Homepage tile |
| `SKILL.md` | Agent Skills front-matter for use outside this project |
