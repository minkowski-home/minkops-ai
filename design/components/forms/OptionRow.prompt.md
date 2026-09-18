Full-width, 48px-min selectable row — the questionnaire funnel's answer control.

```jsx
<OptionRow label="Answering customer support calls & tickets" multi selected onSelect={toggle} />
<OptionRow label="$2,000 – $15,000" meta="Growth" selected={false} onSelect={pick} />
```

Selected = Ember border + Ember wash + filled indicator. Stack in a 8px-gap grid; never side-by-side.
