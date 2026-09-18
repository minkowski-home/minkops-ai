Enable/disable switch — the console's one instant-effect control (agents, teams, settings).

```jsx
<Toggle checked={agent.enabled} onChange={(v) => setEnabled(v)} label="Imel" />
```

On = Ember track. Toggling an agent off leaves it provisioned; it is not an unsubscribe.
