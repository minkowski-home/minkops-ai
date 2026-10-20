/** How the console presents a workflow and which of its run options it may save. */

/** Installed presentation selects a product adapter, independently of identity. */
export type WorkflowPresentation = "accounts-discovery" | "accounts-bill" | "accounts-statement" | "proposal";

export function presentationFor(workflow: { key: string; presentation?: string | null }): WorkflowPresentation | null {
  const declared = workflow.presentation;
  if (declared === "accounts-discovery" || declared === "accounts-bill" || declared === "accounts-statement" || declared === "proposal") return declared;
  if (declared) return null;
  // Compatibility for already loaded workspace snapshots during rollout.
  if (workflow.key === "source-discovery") return "accounts-discovery";
  if (workflow.key === "bill-entry") return "accounts-bill";
  return null;
}

/** Only schema-declared defaults are persisted; resource grants remain run-specific. */
export function defaultableValues(values: Record<string, unknown>, properties: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(values).filter(([key]) => key in properties));
}
