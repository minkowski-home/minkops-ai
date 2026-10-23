import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, type SessionInfo } from "../api";
import { LoadingIndicator, RetryMessage } from "../components/Feedback";
import { useAuth } from "../contexts/AuthContext";
import { useRead } from "../useRead";

function when(value: string) {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** A person's own account: their name, password and sessions, and the workspace they belong to. */
export function ProfileScreen() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const sessions = useRead<SessionInfo[]>(user?.id ?? "", "/api/auth/sessions", { enabled: Boolean(user) });
  const [name, setName] = useState(user?.name ?? "");
  const [password, setPassword] = useState({ current: "", next: "", again: "" });
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  async function act(key: string, path: string, method: string, body?: object) {
    if (!user || busy) return false;
    setBusy(key);
    setNotice("");
    try {
      const answer = await api<{ message?: string }>(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) },
        user.csrf_token);
      setNotice(answer?.message ?? "Saved.");
      await sessions.refresh();
      return true;
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "Could not save this change.");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (await act("name", "/api/auth/me", "PATCH", { name })) {
      setNotice("Name saved.");
      await refresh();
    }
  }

  async function change(event: FormEvent) {
    event.preventDefault();
    if (password.next !== password.again) {
      setNotice("The new passwords differ. Type the same one twice.");
      return;
    }
    if (await act("password", "/api/auth/password", "POST",
      { current_password: password.current, new_password: password.next })) {
      setPassword({ current: "", next: "", again: "" });
    }
  }

  async function end(session: SessionInfo) {
    if (session.current) {
      await logout();
      navigate("/login");
    } else await act(session.id, `/api/auth/sessions/${session.id}`, "DELETE");
  }

  if (!user) return null;
  const membership = user.memberships[0];
  const working = (key: string) => busy === key ? "Saving… " : "";
  return <section className="route-screen"><header className="route-heading"><div>
    <h2>Your account</h2><p>{user.email}</p></div></header>
    {notice && <p role="status" className="form-message">{notice}</p>}
    <div className="detail-grid">
      <form className="config-panel" onSubmit={(event) => void rename(event)}><h3>Your name</h3>
        <label className="config-field">Name<input required minLength={2} maxLength={120} autoComplete="name"
          value={name} onChange={(event) => setName(event.target.value)} /></label>
        <button className="button button-primary" disabled={Boolean(busy) || name.trim() === user.name}>
          {working("name")}Save name</button>
      </form>
      <form className="config-panel" onSubmit={(event) => void change(event)}><h3>Password</h3>
        <label className="config-field">Current password<input required type="password" autoComplete="current-password"
          value={password.current} onChange={(event) => setPassword({ ...password, current: event.target.value })} /></label>
        <label className="config-field">New password<input required minLength={12} type="password" autoComplete="new-password"
          value={password.next} onChange={(event) => setPassword({ ...password, next: event.target.value })} /></label>
        <label className="config-field">New password again<input required minLength={12} type="password"
          autoComplete="new-password" value={password.again}
          onChange={(event) => setPassword({ ...password, again: event.target.value })} /></label>
        <button className="button button-primary" disabled={Boolean(busy)}>{working("password")}Change password</button>
        <small>Changing it signs you out everywhere else.</small>
      </form>
    </div>
    <section className="related-panel" aria-label="Sessions"><h3>Where you are signed in</h3>
      {sessions.loading && <LoadingIndicator>Loading sessions…</LoadingIndicator>}
      {sessions.error && <RetryMessage onRetry={() => void sessions.refresh()}>Could not load your sessions.</RetryMessage>}
      {(sessions.data ?? []).map((session) => <article className="accounts-item" key={session.id}>
        <strong>{session.current ? "This browser" : session.user_agent || "A browser"}</strong>
        <p><small>Signed in {when(session.created_at)} · last used {when(session.last_seen_at)}</small></p>
        <div className="accounts-toolbar">
          <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void end(session)}>
            {working(session.id)}Sign out{session.current ? "" : " there"}</button>
        </div>
      </article>)}
      {(sessions.data ?? []).length > 1 && <button className="button button-ghost" disabled={Boolean(busy)}
        onClick={() => void act("others", "/api/auth/sessions/end-others", "POST")}>
        {working("others")}Sign out of every other session</button>}
    </section>
    <section className="related-panel" aria-label="Workspace"><h3>Your workspace</h3>
      {membership ? <p>{membership.name} · {membership.role === "admin" ? "Admin" : "Member"}</p>
        : <p className="quiet-state">You are not part of a workspace.</p>}
    </section>
  </section>;
}
