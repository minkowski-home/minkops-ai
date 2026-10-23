import { useState, type FormEvent } from "react";
import { api, type Invitation, type Member, type Workspace } from "../api";
import { LoadingIndicator, RetryMessage } from "../components/Feedback";
import { useAuth } from "../contexts/AuthContext";
import { useRead } from "../useRead";

const ROLES = { admin: "Admin", member: "Member" } as const;
type Role = keyof typeof ROLES;

function day(value: string) {
  return new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

/** The workspace's people, for its admins: roles, the workflows each member runs, removal, and invitations.
 * The server keeps the rules (one workspace per person, an admin always kept); this page carries them. */
export function AccessScreen({ workspace }: { workspace: Workspace }) {
  const { user } = useAuth();
  const tenant = workspace.tenant.slug;
  const base = `/api/tenants/${encodeURIComponent(tenant)}`;
  const scope = `${user?.id ?? ""}:${tenant}`;
  const people = useRead<Member[]>(scope, `${base}/members`);
  const invited = useRead<Invitation[]>(scope, `${base}/invitations`);
  const [draft, setDraft] = useState<{ email: string; role: Role }>({ email: "", role: "member" });
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [localLink, setLocalLink] = useState("");
  const [removing, setRemoving] = useState<Member | null>(null);
  // A member's role or workflows being saved show at once, and fall back to the server's if the save fails.
  const [pending, setPending] = useState<Record<string, Partial<Member>>>({});

  async function act(key: string, path: string, method: string, body?: object, done?: (answer: Record<string, unknown>) => string) {
    if (!user || busy) return;
    setBusy(key);
    setNotice("");
    setLocalLink("");
    try {
      const answer = await api<Record<string, unknown>>(base + path,
        { method, ...(body ? { body: JSON.stringify(body) } : {}) }, user.csrf_token);
      setNotice(done ? done(answer) : "Saved.");
      if (typeof answer?.invitation_link === "string") setLocalLink(answer.invitation_link);
      await Promise.all([people.refresh(), invited.refresh()]);
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "Could not save this change.");
    } finally {
      setBusy("");
    }
  }

  function invite(event: FormEvent) {
    event.preventDefault();
    void act("invite", "/invitations", "POST", draft, (answer) => String(answer.message)).then(() =>
      setDraft({ email: "", role: draft.role }));
  }

  function change(member: Member, key: string, update: Partial<Member>, done?: () => string) {
    setPending((current) => ({ ...current, [member.id]: update }));
    void act(key, `/members/${member.id}`, "PATCH", update, done).finally(() => setPending((current) => {
      const next = { ...current };
      delete next[member.id];
      return next;
    }));
  }

  function assign(member: Member, workflowId: string, on: boolean) {
    const ids = on ? [...member.workflow_ids, workflowId] : member.workflow_ids.filter((id) => id !== workflowId);
    change(member, `${member.id}:workflows`, { workflow_ids: ids });
  }

  function promote(member: Member, role: Role) {
    change(member, `${member.id}:role`, { role }, () => `${member.name} is now ${ROLES[role].toLowerCase()}.`);
  }

  const working = (key: string) => busy === key ? "Saving… " : "";
  return <section className="route-screen"><header className="route-heading"><div>
    <h2>Workspace access</h2>
    <p>Who belongs to {workspace.tenant.name}, and the workflows each member runs. Admins run every workflow.</p>
  </div></header>
    {notice && <p role="status" className="form-message">{notice}</p>}
    {localLink && <p className="form-message">Local sign-up link: <a href={localLink}>{localLink}</a></p>}
    <section className="related-panel" aria-label="Members"><h3>Members</h3>
      {people.loading && <LoadingIndicator>Loading members…</LoadingIndicator>}
      {people.error && <RetryMessage onRetry={() => void people.refresh()}>Could not load the members.</RetryMessage>}
      {(people.data ?? []).map((saved) => ({ ...saved, ...pending[saved.id] })).map((member) =>
        <article className="accounts-item" key={member.id}>
        <strong>{member.name}</strong><span> · {member.email}{member.id === user?.id ? " · you" : ""}</span>
        <div className="accounts-toolbar">
          <label className="config-field">Role<select aria-label={`Role of ${member.name}`} value={member.role}
            disabled={Boolean(busy)} onChange={(event) => promote(member, event.target.value as Role)}>
            {Object.entries(ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => setRemoving(member)}>Remove</button>
        </div>
        {member.role === "admin"
          ? <small>Runs every workflow{member.pcs ? ` · ${member.pcs} connected PC${member.pcs === 1 ? "" : "s"}` : ""}</small>
          : <fieldset className="access-workflows" disabled={Boolean(busy)}><legend>Workflows {member.name} runs</legend>
            {workspace.workflows.map((flow) => <label key={flow.id}>
              <input type="checkbox" checked={member.workflow_ids.includes(flow.id)}
                onChange={(event) => assign(member, flow.id, event.target.checked)} />{flow.name}</label>)}
            {!workspace.workflows.length && <small>No workflows installed yet.</small>}
            {working(`${member.id}:workflows`) && <small>Saving…</small>}
            {member.pcs > 0 && <small>{member.pcs} connected PC{member.pcs === 1 ? "" : "s"}</small>}
          </fieldset>}
        {removing?.id === member.id && <div role="alertdialog" aria-label={`Remove ${member.name}`} className="config-panel">
          <p>Remove {member.name} from {workspace.tenant.name}? They are signed out and lose access
            {member.pcs ? `, and their ${member.pcs} connected PC${member.pcs === 1 ? " is" : "s are"} disconnected` : ""}.
            Runs they started carry on for others to review.</p>
          <div className="accounts-toolbar">
            <button className="button button-primary" disabled={Boolean(busy)} onClick={() => void act(`${member.id}:remove`,
              `/members/${member.id}`, "DELETE", undefined, () => `${member.name} was removed.`).then(() => setRemoving(null))}>
              {working(`${member.id}:remove`)}Remove {member.name}</button>
            <button className="button button-ghost" onClick={() => setRemoving(null)}>Keep</button>
          </div>
        </div>}
      </article>)}
    </section>
    <section className="related-panel" aria-label="Invitations"><h3>Invitations</h3>
      {(invited.data ?? []).map((invitation) => <article className="accounts-item" key={invitation.id}>
        <strong>{invitation.email}</strong><span> · {ROLES[invitation.role]}</span>
        <p><small>{invitation.expired ? "Link expired" : `Link works until ${day(invitation.expires_at)}`}
          {invitation.invited_by ? ` · invited by ${invitation.invited_by}` : ""}</small></p>
        <div className="accounts-toolbar">
          <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void act(`${invitation.id}:resend`,
            `/invitations/${invitation.id}/resend`, "POST", undefined, (answer) => String(answer.message))}>
            {working(`${invitation.id}:resend`)}{invitation.expired ? "Send a new link" : "Resend"}</button>
          <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void act(`${invitation.id}:withdraw`,
            `/invitations/${invitation.id}`, "DELETE", undefined, () => "Invitation withdrawn.")}>
            {working(`${invitation.id}:withdraw`)}Withdraw</button>
        </div>
      </article>)}
      {invited.data && !invited.data.length && <p className="quiet-state">No invitations waiting.</p>}
      <form className="config-panel" onSubmit={invite}><h4>Invite someone</h4>
        <label className="config-field">Email<input type="email" required value={draft.email}
          onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label>
        <label className="config-field">Role<select aria-label="Invite as" value={draft.role}
          onChange={(event) => setDraft({ ...draft, role: event.target.value as Role })}>
          {Object.entries(ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <button className="button button-primary" disabled={Boolean(busy)}>{working("invite")}Send invitation</button>
        <small>They get a sign-up link by email. It works once, for seven days. A member runs no workflow until you
          assign one.</small>
      </form>
    </section>
  </section>;
}
