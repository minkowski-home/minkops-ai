import type { SolutionManifest } from "../../packages/solution-contracts/src";

/**
 * Console identity only. Employee installation and tool policy live beside
 * this manifest; workflow implementations remain shared.
 */
export const solution: SolutionManifest = {
  id: "pr-infra",
  displayName: "PR Infra"
};
