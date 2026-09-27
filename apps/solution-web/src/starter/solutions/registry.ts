import type { SolutionManifest } from "@minkops/solution-contracts";
import { solution as mockClient } from "../../../../../solutions/mock-client/solution";
import { solution as prInfra } from "../../../../../solutions/pr-infra/solution";

/**
 * The public host ships a small manifest registry so a single deployment can
 * serve every solution. Authentication will eventually resolve the allowed
 * manifest from tenant membership rather than accepting an arbitrary URL.
 */
const solutions: readonly SolutionManifest[] = [prInfra, mockClient];

export const DEFAULT_SOLUTION_ID = "pr-infra";

export function getSolution(id: string): SolutionManifest | undefined {
  return solutions.find((solution) => solution.id === id);
}
