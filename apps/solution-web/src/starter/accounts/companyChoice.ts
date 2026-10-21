/** The company a Bill Entry run enters, as Source Discovery reported it. */
export interface DiscoveredCompany {
  company: string;
  company_guid: string;
}

/** Never preselect one of several companies: the batch's company is the user's
 * call. A saved choice is kept even when it is no longer discovered, so the run
 * waits for a new choice instead of silently switching companies. */
export function initialLockedCompany(companies: DiscoveredCompany[], configured: unknown) {
  if (typeof configured === "string" && configured) return configured;
  return companies.length === 1 ? companies[0].company_guid : "";
}
