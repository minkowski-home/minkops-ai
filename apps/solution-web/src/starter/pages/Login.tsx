import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type SessionUser } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { ThemePicker } from "../theme/ThemeContext";

function AuthLayout({ title, intro, children }: {
  title: string; intro: string; children: React.ReactNode;
}) {
  return <main className="login-screen">
    <section className="login-story">
      <div className="login-story-top"><Link to="/" className="login-wordmark"><span className="wordmark-dot" />minkops</Link><ThemePicker /></div>
      <div><h1>{title}</h1><p>{intro}</p></div>
      <small>Useful work, clearly in view.</small>
    </section>
    <section className="login-form-panel">{children}</section>
  </main>;
}

/** Where a signed-in person goes: their workspace, or the page saying they have none yet. */
function home(user: SessionUser | null) {
  return user?.memberships[0] ? `/${user.memberships[0].slug}/dashboard`
    : user?.is_platform_admin ? "/pr-infra/dashboard" : "/no-workspace";
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
      navigate(next?.startsWith("/") && !next.startsWith("//") ? next : home(current), { replace: true });
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
      <p><Link to="/reset">Forgot your password?</Link></p>
      <p>New to Minkops? Your workspace's admin sends you an invitation.</p>
    </form>
  </AuthLayout>;
}

interface InvitationView {
  workspace: string;
  email: string;
  role: "admin" | "member";
  expires_at: string;
  account: boolean;
}

/** An invitation's link: a new person creates their account and is signed in; someone with an account signs in
 * first, then joins. */
export function InvitePage() {
  const { token = "" } = useParams();
  const { user, isLoading, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [invitation, setInvitation] = useState<InvitationView | null>(null);
  const [problem, setProblem] = useState("");
  const [form, setForm] = useState({ name: "", password: "", again: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<InvitationView>(`/api/auth/invitations/${encodeURIComponent(token)}`).then(setInvitation)
      .catch((caught) => setProblem(caught instanceof Error ? caught.message : "This invitation link does not work."));
  }, [token]);

  async function join(body: object) {
    setBusy(true);
    setError("");
    try {
      const joined = await api<{ workspace: string }>(`/api/auth/invitations/${encodeURIComponent(token)}/accept`,
        { method: "POST", body: JSON.stringify(body) }, user?.csrf_token);
      await refresh();
      navigate(`/${joined.workspace}/dashboard`, { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not join the workspace.");
    } finally {
      setBusy(false);
    }
  }

  function signUp(event: FormEvent) {
    event.preventDefault();
    if (form.password !== form.again) setError("The passwords differ. Type the same one twice.");
    else void join({ name: form.name, password: form.password });
  }

  const intro = invitation ? `You are invited to ${invitation.workspace} as ${invitation.role === "admin" ? "an admin" : "a member"}.`
    : "A teammate has invited you to work together.";
  return <AuthLayout title="Join your workspace" intro={intro}>
    {problem ? <div className="auth-result"><h2>This link does not work</h2><p role="alert">{problem}</p>
      <Link to="/login">Go to sign in</Link></div>
      : !invitation || isLoading ? <div className="auth-result"><p>Opening your invitation…</p></div>
        : user ? <div className="auth-result">
          <h2>Join {invitation.workspace}</h2>
          {user.email.toLowerCase() === invitation.email
            ? <button className="button button-primary" disabled={busy} onClick={() => void join({})}>
              {busy ? "Joining…" : `Join as ${user.name}`}</button>
            : <><p>This invitation is for {invitation.email}, but you are signed in as {user.email}.</p>
              <button className="button button-ghost" onClick={() => void logout()}>Sign out</button></>}
          {error && <p role="alert" className="form-error">{error}</p>}
        </div>
          : invitation.account ? <div className="auth-result">
            <h2>Sign in to join</h2><p>{invitation.email} already has an account. Sign in, then this link adds you to
              {` ${invitation.workspace}`}.</p>
            <Link className="button button-primary" to={`/login?next=${encodeURIComponent(`/invite/${token}`)}`}>
              Sign in to continue</Link>
          </div>
            : <form onSubmit={signUp}>
              <h2>Create your account</h2>
              <label>Email<input type="email" value={invitation.email} readOnly /></label>
              <label>Your name<input required minLength={2} maxLength={120} autoComplete="name" value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
              <label>Password<input required minLength={12} type="password" autoComplete="new-password"
                value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
              <label>Password again<input required minLength={12} type="password" autoComplete="new-password"
                value={form.again} onChange={(event) => setForm({ ...form, again: event.target.value })} /></label>
              {error && <p role="alert" className="form-error">{error}</p>}
              <button className="button button-primary" disabled={busy}>
                {busy ? "Creating…" : `Create account and join ${invitation.workspace}`}</button>
              <p>Already have an account? <Link to={`/login?next=${encodeURIComponent(`/invite/${token}`)}`}>Sign in</Link></p>
            </form>}
  </AuthLayout>;
}

/** Ask for a password reset link. The answer is the same whether or not an account uses the address. */
export function ResetRequestPage() {
  const [email, setEmail] = useState("");
  const [result, setResult] = useState<{ message: string; reset_link?: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await api("/api/auth/password-reset", { method: "POST", body: JSON.stringify({ email }) }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send a reset link.");
    } finally {
      setBusy(false);
    }
  }
  return <AuthLayout title="Forgot your password?" intro="We email you a link to choose a new one.">
    {result ? <div className="auth-result"><h2>Check your email</h2><p role="status">{result.message}</p>
      <p>The link works once, within the hour.</p>
      {result.reset_link && <Link className="button button-primary" to={new URL(result.reset_link).pathname}>
        Open the local reset link</Link>}
      <Link to="/login">Back to sign in</Link>
    </div> : <form onSubmit={submit}>
      <h2>Reset your password</h2>
      <label>Email<input required type="email" autoComplete="email" value={email}
        onChange={(event) => setEmail(event.target.value)} /></label>
      {error && <p role="alert" className="form-error">{error}</p>}
      <button className="button button-primary" disabled={busy}>{busy ? "Sending…" : "Email me a link"}</button>
      <p><Link to="/login">Back to sign in</Link></p>
    </form>}
  </AuthLayout>;
}

/** Choose a new password from a reset link; every session ends, so the person signs in again. */
export function ResetPage() {
  const { token = "" } = useParams();
  const [form, setForm] = useState({ password: "", again: "" });
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (form.password !== form.again) {
      setError("The passwords differ. Type the same one twice.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const answer = await api<{ message: string }>("/api/auth/password-reset/confirm",
        { method: "POST", body: JSON.stringify({ token, password: form.password }) });
      setDone(answer.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }
  return <AuthLayout title="Choose a new password" intro="It signs you out everywhere, then you sign in with it.">
    {done ? <div className="auth-result"><h2>Password changed</h2><p role="status">{done}</p>
      <Link className="button button-primary" to="/login">Sign in</Link></div>
      : <form onSubmit={submit}>
        <h2>New password</h2>
        <label>New password<input required minLength={12} type="password" autoComplete="new-password"
          value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
        <label>New password again<input required minLength={12} type="password" autoComplete="new-password"
          value={form.again} onChange={(event) => setForm({ ...form, again: event.target.value })} /></label>
        {error && <p role="alert" className="form-error">{error}</p>}
        <button className="button button-primary" disabled={busy}>{busy ? "Saving…" : "Change password"}</button>
        <p><Link to="/reset">Ask for a new link</Link></p>
      </form>}
  </AuthLayout>;
}

/** A signed-in person who belongs to no workspace, such as one removed from theirs. */
export function NoWorkspacePage() {
  const { user, isLoading, logout } = useAuth();
  const navigate = useNavigate();
  if (!isLoading && !user) return <Navigate to="/login" replace />;
  if (user && (user.memberships[0] || user.is_platform_admin)) return <Navigate to={home(user)} replace />;
  return <AuthLayout title="No workspace yet" intro="Your account is not part of a workspace.">
    <div className="auth-result"><h2>Ask for an invitation</h2>
      <p>A workspace's admin invites you with a link. Open it, and you join their workspace.</p>
      <button className="button button-ghost" onClick={() => void logout().then(() => navigate("/login"))}>Sign out</button>
    </div>
  </AuthLayout>;
}
