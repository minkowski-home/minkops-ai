import type { BillResult } from "./types";

/** Inputs with no proposal: awaiting a decision, or deferred to manual handling. */
export function inputsWithoutProposal(result: BillResult | null) {
  const records = result?.records ?? [];
  const proposed = (id: string) => records.some((r) => r.source_file_id === id);
  return {
    unresolved: (result?.unresolved ?? []).filter((i) => !proposed(i.source_file_id)),
    deferred: (result?.deferred ?? []).filter((i) => !proposed(i.source_file_id)),
  };
}
