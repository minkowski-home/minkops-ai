const { Button, Field, Input } = window.MinkopsDesignSystem_6c27f0;

function LoginScreen({ onSignIn }) {
  const [email, setEmail] = React.useState("kartik@minkowskihome.com");
  const [password, setPassword] = React.useState("••••••••");
  const [busy, setBusy] = React.useState(false);

  const submit = (e) => {
    e.preventDefault();
    setBusy(true);
    setTimeout(() => { setBusy(false); onSignIn(); }, 500);
  };

  return (
    <div style={{ height: "100%", display: "grid", gridTemplateColumns: "1.15fr 1fr", background: "var(--surface-page)" }}>
      <section style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "40px 48px", background: "var(--surface-inverse)", color: "var(--text-inverse)" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "9px" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--brand-ember)" }} />
          <span style={{ font: "var(--fw-bold) var(--fs-lg)/1 var(--font-display)", letterSpacing: "var(--ls-wordmark)" }}>minkops</span>
        </span>
        <div style={{ display: "grid", gap: "12px", maxWidth: "22ch" }}>
          <h1 style={{ font: "var(--fw-semibold) var(--fs-3xl)/1.08 var(--font-display)", letterSpacing: "var(--ls-display)", color: "var(--text-inverse)" }}>Welcome back</h1>
          <p style={{ margin: 0, font: "var(--type-body)", color: "var(--text-inverse-muted)", maxWidth: "30ch" }}>Sign in to your operator dashboard. Your fleet has been running while you were away.</p>
        </div>
        <p style={{ margin: 0, font: "var(--type-mono)", color: "var(--text-inverse-muted)" }}>tenant_001 · Minkowski Home</p>
      </section>

      <section style={{ display: "grid", placeItems: "center", padding: "40px" }}>
        <form onSubmit={submit} style={{ width: "min(340px, 100%)", display: "grid", gap: "14px" }}>
          <Field label="Email" htmlFor="login-email">
            <Input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </Field>
          <Field label="Password" htmlFor="login-password">
            <Input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
          <Button type="submit" variant="primary" fullWidth disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
          <p style={{ margin: 0, font: "var(--type-mono)", color: "var(--text-muted)" }}>Access is restricted to authorised tenants only.</p>
        </form>
      </section>
    </div>
  );
}

Object.assign(window, { LoginScreen });
