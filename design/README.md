# Minkops Design System

This package contains the production design-system review prototype for Minkops. It demonstrates the paper-ledger direction, the role-badged 3D Mink agent identity system, the decision and approval workflow, and foundational component states.

## Run locally

Use the package manager from this directory:

```bash
pnpm install
pnpm dev
```

The primary review surface is the Decision Ledger. The Overview, Agents, and Policies navigation items expose the component and token review surface.

## Contents

- `src/` — React implementation and production styling.
- `public/agents/` — role-badged 3D Mink avatar assets.
- `references/` — approved visual direction.
- `design-qa.md` — visual and interaction verification record.

## Quality bar

The system uses semantic visual roles, accessible state labels, keyboard-operable actions, and explicit approval outcomes. The role badge on each agent makes the agent's operational domain recognizable even in compact roster contexts.
