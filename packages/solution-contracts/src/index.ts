/**
 * Console identity shared with customer solution manifests. Employee bindings
 * and workflow-policy.json own capability selection; business rules and
 * integration implementations remain outside this package.
 */

export interface SolutionManifest {
  id: string;
  /** Optional when the customer-facing route differs from its tenant slug. */
  tenantSlug?: string;
  displayName: string;
}
