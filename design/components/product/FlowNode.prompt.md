Builds the orchestration flowcharts on the marketing site: agent → handoff → agent → outcome.

```jsx
<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
  <FlowNode agent="Floc" role="Copywriter" />
  <FlowArrow label="Drafts copy" />
  <FlowNode agent="Ora" role="Visual experience" />
  <FlowArrow label="Generates assets" />
  <FlowNode output label="Published campaign" />
</div>
```

Agent nodes carry a 2px Ember top edge; the final outcome node is a solid graphite block. Handoff labels are mono and verb-first.
