import type { SolutionManifest } from "../../packages/solution-contracts/src";

/**
 * Development fixture for client-level configuration. It inherits the shared
 * starter workspace rather than owning the product's default operator UI.
 */
export const solution: SolutionManifest = {
  id: "mock-client",
  tenantSlug: "mock-tenant",
  displayName: "Starter workspace"
};
