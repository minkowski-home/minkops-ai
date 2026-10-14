/** Purchase voucher type choices for a Bill Entry run.
 *
 * The server pins one discovered purchase type per company (accounts/voucher_types.py)
 * and rejects a locked run it cannot resolve; this mirrors that rule so the
 * launch screen asks only what the server will need and explains why it waits.
 */
export interface VoucherTypeOffer {
  candidates: { name: string; guid: string; used: number }[];
  default: string | null;
}
export interface DiscoveredCompany {
  company: string;
  company_guid: string;
  purchase_voucher_types?: VoucherTypeOffer;
}

export function voucherTypeLaunch(
  companies: DiscoveredCompany[], mode: "locked" | "infer", lockedGuid: string, chosen: Record<string, string>,
) {
  const scope = mode === "locked" ? companies.filter((c) => c.company_guid === lockedGuid) : companies;
  const questions = scope.filter((c) => (c.purchase_voucher_types?.candidates.length ?? 0) > 1);
  const choices: Record<string, string> = {};
  for (const company of questions) {
    const offered = company.purchase_voucher_types!.candidates.map((c) => c.guid);
    const value = [chosen[company.company_guid], company.purchase_voucher_types!.default].find((v) => v && offered.includes(v));
    if (value) choices[company.company_guid] = value;
  }
  // Older catalogs carry no offer; the server then decides on its own.
  const missing = scope.filter((c) => c.purchase_voucher_types && !c.purchase_voucher_types.candidates.length);
  const unchosen = questions.filter((c) => !choices[c.company_guid]);
  const unavailable = (c: DiscoveredCompany) =>
    `${c.company} has no active purchase voucher type in Tally. Activate or create one, then refresh Source Discovery.`;
  return {
    questions,
    choices,
    blocker: mode !== "locked" ? "" : missing.length ? unavailable(missing[0])
      : unchosen.length ? `Choose the purchase voucher type for ${unchosen[0].company}.` : "",
    notice: mode === "locked" ? "" : [...missing, ...unchosen].map((c) =>
      `${c.company}: bills will wait until its purchase voucher type is chosen or available.`).join(" "),
  };
}

/** Never preselect one of several companies: the batch's company is the user's call. */
export function initialLockedCompany(companies: DiscoveredCompany[], configured: unknown) {
  if (typeof configured === "string" && companies.some((c) => c.company_guid === configured)) return configured;
  return companies.length === 1 ? companies[0].company_guid : "";
}
