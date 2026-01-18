# Minkops Brand Guidelines

## Brand Overview
Minkops presents autonomous intelligence with a clean, glassy, and luminous aesthetic. The visual system combines airy neutrals, high-contrast typography, neon accents, and soft atmospheric gradients to convey precision, confidence, and future-forward capability.

## Color System
### Core Palette
- Background: `#f8f9fa`
- Surface (glass): `rgba(255, 255, 255, 0.5)` to `rgba(255, 255, 255, 0.7)`
- Surface border: `rgba(0, 0, 0, 0.05)`
- Text main: `#1a1a1a`
- Text muted: `#666666`
- Primary glow: `#ff0080`
- Secondary glow: `#00bfff`
- CTA / strong contrast: `#000000`

### Accent Palette (Agent Highlights)
- Purple: `#7000ff`
- Gold: `#ffd700`
- Orange: `#ff4500`

### Utility Neutrals
- Ink: `#111111`
- Subtle text: `#999999`
- Soft fill: `#eeeeee`
- Gradient neutrals: `#f3f3f3`, `#e3e3e3`

## Gradients + Light
### Atmospheric Orbs
- Pink orb: `radial-gradient(circle, rgba(255, 0, 128, 0.25) 0%, rgba(255, 255, 255, 0) 70%)`
- Blue orb: `radial-gradient(circle, rgba(0, 191, 255, 0.25) 0%, rgba(255, 255, 255, 0) 70%)`

### Text Gradient
- Hero highlight: `linear-gradient(120deg, #888888, #222222)`

### Video/Media Wash
- Neutral blend: `linear-gradient(45deg, #f3f3f3, #e3e3e3)`
- Agent tint overlay: `linear-gradient(135deg, #f5f5f5 0%, {agentColor}20 100%)`

## Typography
### Typeface
- Primary: Apple SD Gothic Neo (or system equivalent)
- Fallbacks: Inter, Roboto, system sans-serif

### Weights and Sizing
- Logo: 800 weight, letter-spacing `-0.05em`
- Hero headline: 700 weight, `6rem` desktop, `4rem` mobile, letter-spacing `-0.04em`
- Section headline: 700 weight, `3.5rem`
- Body: 400 to 500 weight, `1.25rem` to `1.5rem`
- Utility labels: uppercase, `0.9rem`, letter-spacing `0.1em`

## Material + UI Treatments
### Glassmorphism
- Nav/footer surfaces: blur `12px`
- Backdrop fill: `rgba(255, 255, 255, 0.4)` to `rgba(255, 255, 255, 0.7)`
- Border: `1px solid rgba(0, 0, 0, 0.05)`

### Buttons
- Pill radius: `30px`
- Primary CTA: black fill (`#000000`) with white text
- Hover: scale `1.05`, shadow `0 5px 15px rgba(0, 0, 0, 0.1)`

## Motion
- Orb pulse: `8s` infinite alternate, ease-in-out, subtle scale + opacity
- Scroll cue: `2s` bounce loop
- Hover transitions: `0.2s` to `0.3s` ease

## Layout + Composition
- Centered, hero-first narrative with expansive whitespace.
- 3D agent showcase occupies mid-page, flanked by subtle navigation arrows.
- Sections scale to `80vh` to preserve a gallery-like rhythm.
- Footer mirrors navigation clarity with minimal, structured columns.

## Brand Voice
- Confident, precise, future-forward.
- Emphasize autonomy, orchestration, and enterprise readiness.
- Short, directive headings with crisp supporting lines.

## Token Reference (CSS)
```
--bg-color: #f8f9fa;
--text-main: #1a1a1a;
--text-muted: #666666;
--primary-glow: #ff0080;
--secondary-glow: #00bfff;
--glass-bg: rgba(255, 255, 255, 0.7);
--glass-border: rgba(255, 255, 255, 0.5);
--glass-highlight: rgba(255, 255, 255, 0.9);
```
