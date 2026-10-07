/** Installed presentation selects a product adapter, independently of identity. */
export type WorkflowPresentation = "accounts-discovery" | "accounts-bill" | "proposal";

export function presentationFor(workflow: { key: string; presentation?: string | null }): WorkflowPresentation | null {
  const declared = workflow.presentation;
  if (declared === "accounts-discovery" || declared === "accounts-bill" || declared === "proposal") return declared;
  if (declared) return null;
  // Compatibility for already loaded workspace snapshots during rollout.
  if (workflow.key === "source-discovery") return "accounts-discovery";
  if (workflow.key === "bill-entry") return "accounts-bill";
  return null;
}
