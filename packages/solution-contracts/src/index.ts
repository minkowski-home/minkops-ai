/**
 * Stable composition boundary between the shared product and one customer
 * solution. Keep business rules and integration implementations out of this
 * package: a solution only declares which reusable capabilities it composes.
 */

export type ConsoleRoute = "dashboard" | "agents" | "tasks" | "analytics" | "settings";

export type ConnectorId = "email" | "tally" | "excel" | "ukg" | "whatsapp";

export type ConsoleIconName =
  | "agents"
  | "analytics"
  | "home"
  | "settings"
  | "tasks";

export interface SolutionNavigationItem {
  route: ConsoleRoute;
  label: string;
  icon: ConsoleIconName;
}

export interface SolutionManifest {
  id: string;
  displayName: string;
  enabledConnectors: readonly ConnectorId[];
  ui: {
    productName: string;
    navigation: readonly SolutionNavigationItem[];
    options: {
      showAnalytics: boolean;
      showTeamControls: boolean;
    };
  };
}
