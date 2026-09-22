import type { SolutionManifest, SolutionUiConfig } from "@minkops/solution-contracts";

/**
 * The default operator-workspace anatomy. A client can override labels or hide
 * routes, but a new solution starts with a usable work, review, and activity
 * surface instead of a blank page.
 */
const DEFAULT_UI: SolutionUiConfig = {
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
};

export function resolveStarterUi(solution: SolutionManifest): SolutionUiConfig {
  const override = solution.ui;
  if (!override) return DEFAULT_UI;

  return {
    productName: override.productName || DEFAULT_UI.productName,
    navigation: override.navigation.length ? override.navigation : DEFAULT_UI.navigation,
    options: { ...DEFAULT_UI.options, ...override.options }
  };
}
