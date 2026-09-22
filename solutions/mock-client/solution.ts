import type { SolutionManifest } from "../../packages/solution-contracts/src";

/**
 * Development fixture for client-level configuration. It inherits the shared
 * starter workspace rather than owning the product's default operator UI.
 */
export const solution: SolutionManifest = {
  id: "mock-client",
  displayName: "Starter workspace",
  enabledConnectors: ["email", "excel"],
  ui: {
    productName: "minkops",
    navigation: [
      { route: "dashboard", label: "Dashboard", icon: "home" },
      { route: "agents", label: "Agents", icon: "agents" },
      { route: "workflows", label: "Workflows", icon: "tasks" }
    ],
    options: {
      showAnalytics: false,
      showTeamControls: false
    }
  }
};
