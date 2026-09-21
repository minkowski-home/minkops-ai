import SolutionApp from "@minkops/solution-entry";

/**
 * Client-agnostic build host. Vite aliases a bespoke client UI when present;
 * otherwise it selects the shared starter workspace at build time.
 */
export default function App() {
  return <SolutionApp />;
}
