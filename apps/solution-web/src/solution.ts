import type { SolutionManifest } from "../../../packages/solution-contracts/src";

type SolutionModule = { solution: SolutionManifest };

const availableSolutions = import.meta.glob<SolutionModule>(
  "../../../solutions/*/ui.ts",
  { eager: true }
);

const requestedId = import.meta.env.VITE_SOLUTION ?? "example";
const requestedSuffix = `/solutions/${requestedId}/ui.ts`;
const loadedSolution = Object.entries(availableSolutions).find(([path]) => path.endsWith(requestedSuffix));

if (!loadedSolution) {
  const available = Object.keys(availableSolutions)
    .map((path) => path.split("/").at(-2))
    .filter(Boolean)
    .join(", ");
  throw new Error(`Unknown VITE_SOLUTION "${requestedId}". Available solutions: ${available}.`);
}

export const solution = loadedSolution[1].solution;
