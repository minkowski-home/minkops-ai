import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";

function AuthLayout({ title, intro, children }: {
  title: string; intro: string; children: React.ReactNode;
}) {
  return <main className="login-screen">
    <section className="login-story">
      <Link to="/" className="login-wordmark"><span className="wordmark-dot" />minkops</Link>
      <div><h1>{title}</h1><p>{intro}</p></div>
      <small>Useful work, clearly in view.</small>
    </section>
    <section className="login-form-panel">{children}</section>
  </main>;
}

export default function Login() {
  const { login, refresh } = useAuth();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      const current = await refresh();
      const next = search.get("next");
      navigate(next?.startsWith("/") && !next.startsWith("//") ? next
        : current?.memberships[0] ? `/${current.memberships[0].slug}/dashboard`
        : current?.is_platform_admin ? "/pr-infra/dashboard" : "/join", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return <AuthLayout title="Welcome back" intro="Your workspace is ready when you are.">
    <form onSubmit={submit}>
      <h2>Sign in</h2>
      <label>Email<input required type="email" autoComplete="email" value={email}
        onChange={(event) => setEmail(event.target.value)} /></label>
      <label>Password<input required type="password" autoComplete="current-password" value={password}
        onChange={(event) => setPassword(event.target.value)} /></label>
      {error && <p role="alert" className="form-error">{error}</p>}
      <button className="button button-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      <p>New to Minkops? <Link to="/signup">Create an account</Link></p>
    </form>
  </AuthLayout>;
}

interface SignupResponse {
  message: string;
  suggested_tenant: { slug: string; name: string } | null;
  verification_link?: string;
}

export function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organization, setOrganization] = useState("");
  const [result, setResult] = useState<SignupResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await api<SignupResponse>("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          name, email, password,
          organization_name: organization.trim() || null,
        }),
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-up failed.");
    } finally {
      setBusy(false);
    }
  }

  return <AuthLayout title="Make room for better work" intro="Create your account, then join your workspace.">
    {result ? <div className="auth-result">
      <h2>Check your email</h2><p>{result.message}</p>
      {result.suggested_tenant && <p>We found {result.suggested_tenant.name} from your work email. After verifying, request access to join it.</p>}
      {result.verification_link && <Link className="button button-primary" to={new URL(result.verification_link).pathname}>Verify email locally</Link>}
      <Link to="/login">Go to sign in</Link>
    </div> : <form onSubmit={submit}>
      <h2>Create an account</h2>
      <label>Your name<input required minLength={2} autoComplete="name" value={name}
        onChange={(event) => setName(event.target.value)} /></label>
      <label>Email<input required type="email" autoComplete="email" value={email}
        onChange={(event) => setEmail(event.target.value)} /></label>
      <label>Password<input required minLength={12} type="password" autoComplete="new-password"
        value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <label>New workspace name <span className="optional">optional</span>
        <input value={organization} onChange={(event) => setOrganization(event.target.value)}
          placeholder="Leave blank to join an existing workspace" />
      </label>
      {error && <p role="alert" className="form-error">{error}</p>}
      <button className="button button-primary" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      <p>Already have an account? <Link to="/login">Sign in</Link></p>
    </form>}
  </AuthLayout>;
}

export function VerifyPage() {
  const { token } = useParams();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  async function verify() {
    setBusy(true);
    try {
      const result = await api<{ message: string }>("/api/auth/verify", {
        method: "POST", body: JSON.stringify({ token }),
      });
      setStatus(result.message);
    } catch (caught) {
      setStatus(caught instanceof Error ? caught.message : "Verification failed.");
    } finally { setBusy(false); }
  }
  return <AuthLayout title="One quick check" intro="Confirm that this email belongs to you.">
    <div className="auth-result"><h2>Verify your email</h2>
      <button className="button button-primary" disabled={busy || !!status} onClick={() => void verify()}>
        {busy ? "Verifying…" : "Verify email"}
      </button>
      {status && <p role="status">{status}</p>}
      <Link to="/login">Continue to sign in</Link>
    </div>
  </AuthLayout>;
}

export function InvitePage() {
  const { token } = useParams();
  const { user, refresh } = useAuth();
  const [status, setStatus] = useState("");
  const navigate = useNavigate();
  async function accept() {
    if (!user) return;
    try {
      await api("/api/auth/accept-invite", {
        method: "POST", body: JSON.stringify({ token }),
      }, user.csrf_token);
      const current = await refresh();
      setStatus("Workspace joined.");
      if (current?.memberships[0]) navigate(`/${current.memberships[0].slug}/dashboard`);
    } catch (caught) {
      setStatus(caught instanceof Error ? caught.message : "Invitation failed.");
    }
  }
  return <AuthLayout title="Join your workspace" intro="A teammate has invited you to work together.">
    <div className="auth-result"><h2>Accept invitation</h2>
      {user ? <button className="button button-primary" onClick={() => void accept()}>Join workspace</button>
        : <Link className="button button-primary" to={`/login?next=/invite/${token}`}>Sign in to continue</Link>}
      {status && <p role="status">{status}</p>}
    </div>
  </AuthLayout>;
}

export function JoinPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [slug, setSlug] = useState("");
  const [status, setStatus] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    try {
      const result = await api<{ message: string }>(`/api/tenants/${encodeURIComponent(slug)}/join-requests`,
        { method: "POST" }, user.csrf_token);
      setStatus(result.message);
    } catch (caught) { setStatus(caught instanceof Error ? caught.message : "Request failed."); }
  }
  if (!user) return <AuthLayout title="Find your workspace" intro="Sign in to request access.">
    <Link className="button button-primary" to="/login">Sign in</Link>
  </AuthLayout>;
  return <AuthLayout title={`Hello, ${user.name.split(" ")[0]}`} intro="Ask to join an existing workspace.">
    <form onSubmit={submit}><h2>Request access</h2>
      <label>Workspace ID<input required value={slug} onChange={(event) => setSlug(event.target.value)}
        placeholder="e.g. pr-infra" /></label>
      <button className="button button-primary">Send request</button>
      {status && <p role="status">{status}</p>}
      {user.memberships.map((membership) => <button className="button button-ghost"
        key={membership.slug} type="button" onClick={() => navigate(`/${membership.slug}/dashboard`)}>
        Open {membership.name}
      </button>)}
    </form>
  </AuthLayout>;
}
