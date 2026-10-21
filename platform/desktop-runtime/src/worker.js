/** Reusable local dispatch control; adapters supply network and file effects. */
export class CompanionWorker {
  constructor({
    request,
    execute,
    pending,
    savePending,
    acknowledge = async () => {},
    diagnosticFor = () => null,
    heartbeat = async () => {},
    afterTick = async () => {},
  }) {
    Object.assign(this, {
      request,
      execute,
      pending,
      savePending,
      acknowledge,
      diagnosticFor,
      heartbeat,
      afterTick,
    });
    this.busy = false;
    this.beating = false;
  }
  async reportPresence() {
    if (this.beating) return;
    this.beating = true;
    try {
      await this.heartbeat();
    } finally {
      this.beating = false;
    }
  }
  async tick() {
    // Presence must not claim another job or renew an execution lease. Keep it
    // independent of long native reads, durable receipts and local archiving.
    if (this.busy) return this.reportPresence();
    this.busy = true;
    try {
      if (this.pending()) await this.reportPresence();
      await this.dispatch();
      await this.afterTick();
    } finally {
      this.busy = false;
    }
  }
  async dispatch() {
    let pending = this.pending();
    if (!pending) {
      const job = await this.request("/api/desktop/worker/claim", {});
      if (!job) return;
      let receipt;
      try {
        receipt = {
          claim_token: job.claim_token,
          result: await this.execute(job),
          error: null,
        };
      } catch (error) {
        receipt = {
          claim_token: job.claim_token,
          result: null,
          // Connector errors flagged user-safe carry one specific action (for
          // example "Tally isn't open on <PC>"); anything else stays generic.
          error: error.code === "TASK_STOPPED" ? "Stopped by operator." :
            error.userSafe && typeof error.message === "string" && error.message.trim()
              ? error.message.slice(0, 300)
            : job.operation === "tally.probe"
              ? "Tally could not be checked on this PC. Use Send diagnostics in the Minkops tray menu, then try again."
              : ["tally.save", "tally.statement", "tally.write"].includes(job.operation)
                ? "Tally could not confirm this entry. Check the company, then use Retry save; existing vouchers are reconciled before writing."
                : "The connected folder could not be read. Reconnect it and try again.",
        };
      }
      // Evidence collected while the job ran (for example a classified Tally
      // failure) is sent with the receipt so support never needs the PC.
      const diagnostic = await Promise.resolve()
        .then(() => this.diagnosticFor(job, receipt))
        .catch(() => null);
      if (diagnostic) receipt.diagnostic = diagnostic;
      pending = { id: job.id, receipt };
      await this.savePending(pending);
    }
    try {
      await this.request(
        `/api/desktop/worker/jobs/${pending.id}/finish`,
        pending.receipt,
      );
    } catch (error) {
      // A superseded attempt is terminal; network failures retain the receipt.
      if ([413, 422].includes(error.status) && !pending.receipt.error) {
        // A rejected result must become an observable failure, not an endless
        // reclaim loop. Persist the small error receipt before trying again.
        pending = {
          id: pending.id,
          receipt: {
            claim_token: pending.receipt.claim_token,
            result: null,
            error:
              "The collected result could not be accepted. Choose a smaller supported scope and start again.",
          },
        };
        await this.savePending(pending);
        await this.request(
          `/api/desktop/worker/jobs/${pending.id}/finish`,
          pending.receipt,
        );
        await this.savePending(null);
        return;
      }
      if ([404, 409, 422].includes(error.status))
        await this.savePending(null);
      throw error;
    }
    if (!pending.receipt.error) await this.acknowledge(pending.id);
    await this.savePending(null);
  }
}
