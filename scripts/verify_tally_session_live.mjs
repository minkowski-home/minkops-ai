/** Read-only rehearsal check of the user's Tally session on a Windows PC.
 *
 * Prints the typed state Check connection, discovery and saves would see, and
 * optionally whether one company is open as the discovered one. It never
 * starts, closes or writes to Tally. Usage:
 *   node scripts/verify_tally_session_live.mjs [port] [company] [company-guid]
 */
import { hostname } from "node:os";
import { checkTally, requireOpenCompany } from "../connectors/desktop/src/index.js";

const [port = "9000", company, guid] = process.argv.slice(2);
const options = { port: Number(port), pc: hostname() };
try {
  const ready = await checkTally(options);
  console.log(JSON.stringify(ready, null, 2));
  if (company) console.log(JSON.stringify(await requireOpenCompany({ company, company_guid: guid }, options)));
} catch (error) {
  console.log(JSON.stringify({ state: error.tallyState ?? "error", message: error.message, detail: error.detail }, null, 2));
  process.exitCode = 1;
}
