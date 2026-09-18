const { Eyebrow, Card, EmptyState, Icon, StatusDot, Badge } = window.MinkopsDesignSystem_6c27f0;

/* Analytics and Settings exist as routes in the product but have no designed
   screens in the source codebase. They are left intentionally blank here. */
function PlaceholderScreen({ route }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px", display: "grid", gap: "18px", alignContent: "start" }}>
      <div style={{ display: "grid", gap: "6px" }}>
        <Eyebrow rule>{route}</Eyebrow>
        <h2 style={{ font: "var(--type-h2)" }}>{route === "analytics" ? "Analytics" : "Settings"}</h2>
      </div>
      <Card tone="sunken" pad="0">
        <EmptyState icon={<Icon name={route === "analytics" ? "analytics" : "settings"} size={20} />}
          headline="Not designed yet"
          hint={"The Minkops codebase routes to /" + route + " but ships no screen for it. Left blank on purpose rather than invented."} />
      </Card>
      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
        <Badge tone="neutral">Route present</Badge>
        <StatusDot status="idle" label="no source design" />
      </div>
    </div>
  );
}

Object.assign(window, { PlaceholderScreen });
