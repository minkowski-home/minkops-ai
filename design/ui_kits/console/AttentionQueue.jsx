const { InterruptCard, PriorityPill, EmptyState } = window.MinkopsDesignSystem_6c27f0;

const ORDER = ["critical", "high", "medium", "low"];

function AttentionQueue({ interrupts, onResolve, onAcknowledge, onDismiss }) {
  const pending = interrupts.filter((i) => i.status === "pending");
  const counts = ORDER.map((l) => [l, pending.filter((i) => i.priority === l).length]).filter(([, n]) => n > 0);
  const sorted = [...interrupts].sort((a, b) =>
    ORDER.indexOf(a.priority) - ORDER.indexOf(b.priority) ||
    (a.status === b.status ? 0 : a.status === "pending" ? -1 : 1)
  );

  return (
    <section style={{ width: "var(--pane-attention-w)", flex: "none", display: "flex", flexDirection: "column", borderLeft: "1px solid var(--border-hairline)", background: "var(--surface-sunken)", minHeight: 0 }}>
      <PaneHeader title={"Needs attention" + (pending.length ? " (" + pending.length + ")" : "")} />
      {counts.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", padding: "10px 12px 0" }}>
          {counts.map(([l, n]) => <PriorityPill key={l} level={l} count={n} />)}
        </div>
      ) : null}
      <div style={{ overflowY: "auto", padding: "10px 12px 14px", display: "grid", gap: "10px", alignContent: "start" }}>
        {sorted.length === 0 ? (
          <EmptyState headline="All clear" hint="No items need your attention right now. Agents are running smoothly." />
        ) : sorted.map((i) => (
          <InterruptCard key={i.id} {...i}
            onResolve={() => onResolve(i.id)}
            onAcknowledge={() => onAcknowledge(i.id)}
            onDismiss={() => onDismiss(i.id)} />
        ))}
      </div>
    </section>
  );
}

Object.assign(window, { AttentionQueue });
