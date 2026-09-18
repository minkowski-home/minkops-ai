const { MessageBubble, TypingIndicator, Textarea, IconButton, Icon, StatusDot, EmptyState } = window.MinkopsDesignSystem_6c27f0;

function TaskThread({ messages, activeCount, onSend }) {
  const [draft, setDraft] = React.useState("");
  const [working, setWorking] = React.useState(false);
  const listRef = React.useRef(null);

  React.useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, working]);

  const send = () => {
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    onSend(content);
    setWorking(true);
    setTimeout(() => setWorking(false), 1600);
  };

  return (
    <section style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, background: "var(--surface-page)" }}>
      <PaneHeader title="Assign a task" meta={
        <span style={{ marginLeft: "6px" }}><StatusDot status="active" pulse label={activeCount + " agents active"} /></span>
      } />
      <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: "16px 18px", display: "grid", gap: "14px", alignContent: "start" }}>
        {messages.length === 0 ? (
          <EmptyState icon={<Icon name="agents" size={20} />} headline="No tasks yet" hint="Type a task below and your agents will get to work immediately." />
        ) : messages.map((m) => <MessageBubble key={m.id} {...m} />)}
        {working ? <TypingIndicator name="Imel" /> : null}
      </div>
      <div style={{ flex: "none", padding: "10px 14px 12px", borderTop: "1px solid var(--border-hairline)", background: "var(--surface-page)" }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: "8px" }}>
          <Textarea autoGrow rows={1} value={draft} placeholder="Describe a task for your agents…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <IconButton label="Send task" size={38} onClick={send}
            style={{ background: draft.trim() ? "var(--action-primary-bg)" : "var(--action-disabled-bg)", color: draft.trim() ? "var(--action-primary-fg)" : "var(--action-disabled-fg)", border: "1px solid transparent" }}>
            <Icon name="send" size={15} />
          </IconButton>
        </div>
        <p style={{ margin: "6px 0 0", font: "var(--type-mono)", color: "var(--text-faint)" }}>Enter to send · Shift+Enter for new line</p>
      </div>
    </section>
  );
}

Object.assign(window, { TaskThread });
