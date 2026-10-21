/** What each companion job does, shared by the Electron shell and the headless
 * development runner, so both execute exactly the same native work.
 *
 * Adapters are injected: the native connectors, the authenticated server
 * request, folder grants, the durable intent store and diagnostics. Business
 * authority stays with the server; every write plan arrives from it and every
 * outcome goes back as a receipt.
 */
import { collectSources, reportDiscoveryProgress } from "./discovery.js";

const PAGE_RETRIES = [1000, 3000, 10000, 30000];

/** Send one sync page, retrying only transport failures with the same sequence. */
export async function uploadWithRetry(send, page, { wait = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
  for (let attempt = 0; ; attempt++) {
    try {
      return await send(page);
    } catch (error) {
      // The server answered: a rejected page or a replaced claim is final.
      if (error.status || attempt >= PAGE_RETRIES.length) throw error;
      await wait(PAGE_RETRIES[attempt]);
    }
  }
}

export function createExecutor({ connectors, request, pc, grantFor, durableIntent, saveDiscovery, transportFor,
                                 recordDiagnostic = () => {}, planVersion }) {
  const plan = (job) => request(`/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`);
  return async function execute(job) {
    // Minkops never starts, closes or restarts Tally; failures become typed
    // states naming this PC, and each one leaves a local diagnostic record.
    const tallyRequest = transportFor(job);
    if (job.operation === "tally.probe" && !Object.keys(job.input || {}).length) {
      // Check connection uses the same read-only check as syncs and saves.
      try {
        const ready = await connectors.checkTally({ pc });
        return { available: true, companies: ready.companies.map((c) => c.company) };
      } catch (error) {
        recordDiagnostic(job, { state: error.tallyState ?? "error", cause: error.detail?.cause,
          running: error.detail?.running, error: String(error.message).slice(0, 300) });
        throw error;
      }
    }
    if (job.operation === "tally.sync") {
      let seq = 0;
      const upload = (kind, body) => uploadWithRetry(
        (page) => request(`/api/desktop/worker/jobs/${job.id}/sync`, page),
        { claim_token: job.claim_token, seq: seq++, kind, ...body });
      return connectors.runSync(await plan(job), { request: tallyRequest, upload, pc });
    }
    if (job.operation === "sources.discover") {
      const collection = await plan(job);
      const result = await collectSources(collection, {
        folderFor: (id) => grantFor(id).root,
        inventory: connectors.inventory,
        inspectExcel: connectors.inspectExcel,
        excelSchemaBytes: connectors.excelSchemaBytes,
        discoverClientContext: (config, options) =>
          connectors.discoverClientContext(config, { ...options, request: tallyRequest, pc }),
        onProgress: async (source_key, status, category = null, progress = null) => {
          try {
            await reportDiscoveryProgress(() => request(`/api/desktop/worker/jobs/${job.id}/progress`, {
              claim_token: job.claim_token, source_key, status, category, ...(progress ? { progress } : {}),
            }));
          } catch (error) {
            if (error.code === "TASK_STOPPED" || [401, 404, 409].includes(error.status)) throw error;
          }
        },
      });
      await saveDiscovery(job, result);
      return result;
    }
    if (job.operation === "files.refresh") return { files: await connectors.inventory(grantFor(job.input.source_id).root) };
    if (job.operation === "attention.refresh" || job.operation === "attention.supplier" || job.operation === "tally.supplier")
      return connectors.inspectTallyAttention(await plan(job),
        { request: tallyRequest, createSupplier: job.operation !== "attention.refresh" });
    if (job.operation === "tally.write" || job.operation === "tally.save") {
      const voucher = await plan(job);
      if (voucher.format_version > planVersion) throw new Error("Unsupported voucher plan.");
      return connectors.saveVoucher(voucher, { request: tallyRequest, beforeImport: durableIntent(job), pc,
        diagnose: (record) => recordDiagnostic(job, record) });
    }
    throw new Error("Unsupported local operation.");
  };
}
