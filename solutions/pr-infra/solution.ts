import type { SolutionManifest } from "../../packages/solution-contracts/src";

/**
 * Composition only. PR Infra starts with the shared starter workspace and no
 * bespoke UI, workflow implementation, or customer-specific data.
 */
export const solution: SolutionManifest = {
  id: "pr-infra",
  displayName: "PR Infra",
  enabledConnectors: ["whatsapp", "excel"]
};
