import { useState } from "react";
import { api, type Workflow } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { Spinner } from "../components/Feedback";
import { presentationFor } from "./presentation";
import { defaultableValues } from "./runSettings";

export interface RunSettingsActions {
  canEdit: boolean;
  savedValues: Workflow["config_values"];
  onSaved: () => Promise<void>;
}
export interface RunSettingsProps {
  tenant: string;
  workflow: Workflow;
  onConfigChange?: (values: Workflow["config_values"]) => void;
  settings?: RunSettingsActions;
}
const labels: Record<string, string> = {
  excel_in_place: "Excel", tally_in_place: "Tally", both_in_place: "Both",
  draft_excel: "Excel draft", all_outputs: "Approve every output",
  only_exceptions: "Only exceptions", pdf: "PDFs", image: "Images", mixed: "PDFs and images",
};
export function RunSettings({ tenant, workflow, onConfigChange, settings, exclude = [], busy = false, onReset, description }: RunSettingsProps & {
  exclude?: string[]; busy?: boolean; onReset?: () => void; description?: string;
}) {
  const { user } = useAuth();
  const [saving, setSaving] = useState(false), [message, setMessage] = useState("");
  const properties = workflow.config_schema.properties;
  const fields = Object.entries(properties).filter(([key]) => !exclude.includes(key));
  const disabled = busy || saving;
  async function save() {
    if (!user || !settings?.canEdit || disabled) return;
    setSaving(true); setMessage("");
    try {
      await api(`/api/tenants/${encodeURIComponent(tenant)}/workflows/${workflow.id}`, {
        method: "PATCH", body: JSON.stringify({config_values: defaultableValues(workflow.config_values, properties)}),
      }, user.csrf_token);
      await settings.onSaved(); setMessage("Defaults saved. This run keeps your selected options.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save defaults."); }
    finally { setSaving(false); }
  }
  function update(key: string, value: string | number | boolean) {
    setMessage(""); onConfigChange?.({...workflow.config_values, [key]: value});
  }
  return <section className="run-settings" aria-label="Run options">
    {fields.length > 0 && <h4>Run options</h4>}
    <p className="quiet-state">{description ?? "Changes apply to the next run. Save as defaults to reuse supported options."}</p>
    {fields.length > 0 && <div className="accounts-field-grid">{fields.map(([key, spec]) => {
      const title = key === "review_mode" ? "Review mode" : key === "output_mode" && presentationFor(workflow) === "accounts-bill" ? "Save bills to" : spec.title ?? key;
      return <label className="config-field" key={key}><span>{title}</span>{spec.description && <small>{spec.description}</small>}
        {spec.enum ? <select aria-label={title} value={String(workflow.config_values[key] ?? "")} disabled={disabled}
          onChange={event => update(key, event.target.value)}>
          {spec.enum.filter(option => !spec['x-enabled-options'] || spec['x-enabled-options'].includes(option)).map(option =>
            <option key={String(option)} value={String(option)}>{labels[String(option)] ?? option}</option>)}
        </select> : spec.type === "boolean" ? <input type="checkbox" checked={Boolean(workflow.config_values[key])} disabled={disabled} onChange={event => update(key, event.target.checked)} />
          : <input aria-label={title} type={spec.type === "integer" ? "number" : "text"} value={String(workflow.config_values[key] ?? "")} disabled={disabled}
            onChange={event => update(key, spec.type === "integer" ? Number(event.target.value) : event.target.value)} />}
      </label>;
    })}</div>}
    {workflow.config_values.review_mode && <p className="quiet-state">{presentationFor(workflow) !== "accounts-bill" ? "Review follows this workflow’s execution rules and client policies." : workflow.config_values.review_mode === "only_exceptions"
      ? "Eligible bills without findings are saved automatically. Exceptions and client policy requirements still need review."
      : "Approve proposed outputs before they are saved."}</p>}
    <div className="accounts-toolbar">
      {settings?.canEdit && <button type="button" className="button button-ghost" disabled={disabled} onClick={() => void save()}>{saving && <Spinner />}Save as defaults</button>}
      {settings && <button type="button" className="button button-ghost" disabled={disabled} onClick={() => {onConfigChange?.({...settings.savedValues}); onReset?.(); setMessage("Saved defaults restored.");}}>Reset to defaults</button>}
    </div>
    {message && <p role="status" className="form-message">{message}</p>}
  </section>;
}
