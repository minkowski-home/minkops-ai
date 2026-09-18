The unit of the "Needs attention" pane — Minkops' human-in-the-loop primitive.

```jsx
<InterruptCard type="approval" priority="high" title="Approve refund: Acme Corp — $3,200"
  description="Imel drafted a refund approval for ticket #2847…" agentName="Imel"
  taskTitle="Acme Corp refund request #2847" time="8m ago"
  suggestedAction="Review the drafted email and approve or modify the refund amount."
  onResolve={…} onAcknowledge={…} onDismiss={…} />
```

Left edge: Ember while pending, alert-red when critical, grey once acknowledged. Three actions, always in this order: Resolve (primary), Acknowledge, Dismiss (icon-only, right-aligned).
