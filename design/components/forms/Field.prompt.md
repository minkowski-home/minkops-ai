Label + control + hint/error wrapper. Every input in Minkops sits in a Field.

```jsx
<Field label="Work email" htmlFor="email" required hint="We only use this to send your access link.">
  <Input id="email" type="email" placeholder="you@company.com" />
</Field>
```

Labels above the control, always. Never use placeholder text as the label.
