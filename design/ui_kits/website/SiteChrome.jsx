const { Button, Eyebrow } = window.MinkopsDesignSystem_6c27f0;

const PAGES = [
  { key: "agents", label: "Agents" },
  { key: "orchestration", label: "Orchestration" },
  { key: "about", label: "About" },
  { key: "blog", label: "Blog" },
  { key: "careers", label: "Careers" }
];

function SiteNav({ route, onRoute }) {
  return (
    <nav style={{
      position: "sticky", top: 0, zIndex: 5, display: "flex", alignItems: "center", gap: "8px",
      height: "var(--site-nav-h)", padding: "0 32px", background: "var(--surface-page)",
      borderBottom: "1px solid var(--border-hairline)"
    }}>
      <button type="button" onClick={() => onRoute("agents")}
        style={{ display: "flex", alignItems: "center", gap: "9px", background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--brand-ember)" }} />
        <span style={{ font: "var(--fw-bold) var(--fs-lg)/1 var(--font-display)", letterSpacing: "var(--ls-wordmark)", color: "var(--text-primary)" }}>minkops</span>
      </button>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "4px" }}>
        {PAGES.map((p) => (
          <button key={p.key} type="button" onClick={() => onRoute(p.key)}
            style={{
              padding: "7px 11px", background: "none", border: "none", cursor: "pointer",
              borderRadius: "var(--radius-2)",
              font: "var(--fw-medium) var(--fs-sm)/1 var(--font-text)",
              color: route === p.key ? "var(--text-primary)" : "var(--text-secondary)",
              boxShadow: route === p.key ? "inset 0 -2px 0 var(--brand-ember)" : "none"
            }}>{p.label}</button>
        ))}
        <span style={{ marginLeft: "10px" }}>
          <Button variant="primary" size="md" onClick={() => onRoute("access")}>Get access</Button>
        </span>
      </div>
    </nav>
  );
}

const FOOTER_COLS = [
  { head: "Platform", links: ["Agents", "Orchestration", "Pricing"] },
  { head: "Company", links: ["About us", "Careers", "Blog", "info@minkops.com", "hr@minkops.com", "LinkedIn"] },
  { head: "More from the family", links: ["Myndral", "Minkowski Home"] }
];

function SiteFooter() {
  return (
    <footer style={{ background: "var(--surface-inverse)", color: "var(--text-inverse)", padding: "56px 32px 24px" }}>
      <div style={{ maxWidth: "var(--container-w)", margin: "0 auto", display: "grid", gridTemplateColumns: "1.4fr repeat(3, 1fr)", gap: "32px" }}>
        <div style={{ display: "grid", gap: "12px", alignContent: "start" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "9px" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--brand-ember)" }} />
            <span style={{ font: "var(--fw-bold) var(--fs-lg)/1 var(--font-display)", letterSpacing: "var(--ls-wordmark)" }}>minkops</span>
          </span>
          <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-inverse-muted)" }}>Operating system for zero-man companies</p>
          <address style={{ font: "var(--type-mono)", color: "var(--text-inverse-muted)", fontStyle: "normal", lineHeight: 1.7 }}>
            375 University Avenue Suite 3215<br />Toronto, ON M5G 2J5<br />Canada
          </address>
        </div>
        {FOOTER_COLS.map((c) => (
          <div key={c.head} style={{ display: "grid", gap: "9px", alignContent: "start" }}>
            <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-eyebrow)", textTransform: "uppercase", color: "var(--text-inverse-muted)" }}>{c.head}</span>
            {c.links.map((l) => (
              <a key={l} href="#" style={{ font: "var(--type-body-sm)", color: "var(--text-inverse)", borderBottom: "none" }}>{l}</a>
            ))}
          </div>
        ))}
      </div>
      <div style={{ maxWidth: "var(--container-w)", margin: "40px auto 0", paddingTop: "16px", borderTop: "1px solid var(--border-inverse)", display: "flex", gap: "16px", flexWrap: "wrap" }}>
        <p style={{ margin: 0, font: "var(--type-mono)", color: "var(--text-inverse-muted)" }}>© 2026 Minkops. A product of Minkowski Home. All rights reserved.</p>
        <span style={{ marginLeft: "auto", display: "flex", gap: "16px" }}>
          <a href="#" style={{ font: "var(--type-mono)", color: "var(--text-inverse-muted)", borderBottom: "none" }}>Privacy policy</a>
          <a href="#" style={{ font: "var(--type-mono)", color: "var(--text-inverse-muted)", borderBottom: "none" }}>Terms of service</a>
        </span>
      </div>
    </footer>
  );
}

function Section({ eyebrow, title, lead, children, tone = "page" }) {
  return (
    <section style={{ padding: "var(--pad-section)", background: tone === "sunken" ? "var(--surface-sunken)" : "var(--surface-page)", borderTop: "1px solid var(--border-hairline)" }}>
      <div style={{ maxWidth: "var(--container-w)", margin: "0 auto", display: "grid", gap: "28px" }}>
        {(eyebrow || title) ? (
          <div style={{ display: "grid", gap: "12px", maxWidth: "var(--measure)" }}>
            {eyebrow ? <Eyebrow rule>{eyebrow}</Eyebrow> : null}
            {title ? <h2 style={{ font: "var(--type-h1)" }}>{title}</h2> : null}
            {lead ? <p style={{ margin: 0, font: "var(--type-body-lg)", color: "var(--text-secondary)" }}>{lead}</p> : null}
          </div>
        ) : null}
        {children}
      </div>
    </section>
  );
}

Object.assign(window, { SiteNav, SiteFooter, Section, SITE_PAGES: PAGES });
