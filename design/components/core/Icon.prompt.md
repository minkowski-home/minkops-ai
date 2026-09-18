Renders a Minkops glyph inline with `currentColor` — the only icon source in the system.

```jsx
<Icon name="bell" size={18} />
<Icon name="email" size={22} />   {/* agent role glyph */}
```

Two families share one component: 13 UI glyphs (nav, actions, chevrons) at 1.8–2.2 stroke, and 11 agent role glyphs (a person plus a role modifier) at 1.65 stroke. Colour comes from the parent's `color`. Never substitute another icon library.
