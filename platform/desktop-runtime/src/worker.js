/** Reusable local dispatch control; adapters supply network and file effects. */
export class CompanionWorker {
  constructor({
    request,
    execute,
    pending,
    savePending,
    acknowledge = async () => {},
  }) {
    Object.assign(this, {
      request,
      execute,
      pending,
      savePending,
      acknowledge,
    });
    this.busy = false;
  }
  async tick() {
    if (this.busy) return;
    this.busy = true;
    try {
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
        } catch {
          receipt = {
            claim_token: job.claim_token,
            result: null,
            error:
              job.operation === "tally.probe"
                ? "Tally is not responding. Open Tally, load your company, and try again."
                : job.operation === "tally.save"
                  ? "Tally could not confirm this bill. Check the company and resume; existing vouchers will be reconciled before writing."
                  : job.operation === "accounts.save"
                  ? "The workbook could not be saved. Close Excel, check the original folder, and select Resume saves."
                  : "The connected folder could not be read. Reconnect it and try again.",
          };
        }
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
    } finally {
      this.busy = false;
    }
  }
}
