import type { SolutionManifest } from "@minkops/solution-contracts";
/** Build-time discovery includes repository solution manifests without app edits.
 * Membership and server authorization remain authoritative for customer access. */
const modules = import.meta.glob<{ solution: SolutionManifest }>(
  "../../../../../solutions/*/solution.ts", { eager: true }
);
const solutions = Object.values(modules).map((module) => module.solution);

export const DEFAULT_SOLUTION_ID = "pr-infra";

export function getSolution(id: string): SolutionManifest | undefined {
  return solutions.find((solution) => solution.id === id);
}
