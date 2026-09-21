import type { SolutionManifest } from "../../packages/solution-contracts/src";

/**
 * Safe local solution used for development. Create a new sibling directory for
 * each customer; do not fork the web or API applications to change its UI.
 */
export const solution: SolutionManifest = {
  id: "example",
  displayName: "Example Operations",
  enabledConnectors: ["email", "excel"],
  ui: {
    productName: "minkops",
    navigation: [
      { route: "dashboard", label: "Dashboard", icon: "home" },
      { route: "agents", label: "Agents", icon: "agents" },
      { route: "tasks", label: "Work", icon: "tasks" },
      { route: "analytics", label: "Analytics", icon: "analytics" },
      { route: "settings", label: "Settings", icon: "settings" }
    ],
    options: {
      showAnalytics: true,
      showTeamControls: true
    }
  }
};
