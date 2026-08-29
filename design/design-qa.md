# Design QA — Minkops Decision Ledger

## Comparison target

- Source visual truth: `references/decision-ledger-reference.png`.
- Implementation capture: captured locally during browser QA; see the comparison notes below.
- Viewport: 1440 × 1024 CSS pixels, device pixel ratio 2. The implementation capture is browser-rendered at this viewport.
- State: approved refund; the pre-action ledger state and system-review surface were also exercised.

## Full-view comparison

The implementation preserves the source’s principal structure: parchment canvas, narrow agent rail, chronological ledger, decision/evidence module, and operator approval panel. It intentionally replaces photorealistic avatar art with the approved 3D-cartoon Mink identity system and adds small role badges to the scarf/collar of each agent. The approval drawer was present and measured at `x: 1042, width: 382` within the 1440px viewport; the rendered capture exporter clips its rightmost region, not the layout.

## Focused checks

The source and implementation were opened together for visual comparison. The review examined the decision title/evidence card, agent rail with role-badged Mink avatars, navigation selection, approval state, and action hierarchy.

## Required fidelity surfaces

- Fonts and typography: Fraunces provides the source-like editorial display voice, while DM Sans maintains compact UI readability. Heading, metadata, and evidence hierarchy remain distinct and readable.
- Spacing and layout rhythm: a corrected grid placement makes the ledger event body occupy the intended center column; the decision card measures 581px wide at the review viewport.
- Colors and visual tokens: warm parchment, dark brown ink, terracotta primary action, pale green confirmation, and quiet beige dividers follow the selected paper-ledger direction.
- Image quality and asset fidelity: all five agent avatars use generated, consistent 3D-cartoon Mink renders. Each carries a role badge: support chat, billing receipt, fraud shield, logistics parcel, or data sparkle.
- Copy and content: the visible agent, refund, evidence, and decision copy is coherent and supports the review flow.

## Interaction checks

- Agent selection, navigation, and the system-review surface respond to clicks.
- Approving the refund changes the state to `Approved`, disables the completed primary action, and shows the confirmation message `Refund approved — Mira will issue payment.`
- Browser console: no errors observed.

## Comparison history

1. Initial capture revealed the event body was placed in the timeline grid column, collapsing the decision record. Fixed by explicitly assigning `.event-body` to grid column 3.
2. Re-captured at 1440 × 1024. The decision card measured 581px and the approval drawer remained inside the desktop viewport.

## Follow-up polish

- P3: The source uses a more compressed agent list and a slightly more compact approval card. Keep this implementation’s slightly roomier reading rhythm unless usability testing calls for a denser operational view.

final result: passed
