/** Run a bounded collection plan. One unavailable source never hides others. */
import { createHash } from "node:crypto";

/** Pause between reads while renewing the existing claim, never replaying a save. */
export async function reportDiscoveryProgress(report, { wait = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  let paused = false;
  for (;;) {
    let observation;
    try { observation = await report(); }
    catch (error) {
      // A lost connection cannot release an acknowledged pause. Revocation
      // and a replaced claim still terminate this attempt immediately.
      if (!paused || [401, 404, 409].includes(error.status)) throw error;
      await wait(2000);
      continue;
    }
    if (observation?.control_state === "stopped")
      throw Object.assign(new Error("Stopped by operator."), { code: "TASK_STOPPED" });
    if (observation?.control_state !== "paused") return;
    paused = true;
    await wait(2000);
  }
}

export async function collectSources(
  plan,
  { folderFor, inventory, inspectExcel, discoverClientContext, excelSchemaBytes, onProgress },
) {
  const sources = [];
  let selectedBytes = 0,
    selectedFiles = 0;
  for (const source of plan.sources) {
    let currentProgress;
    await onProgress(source.key, "reading");
    try {
      if (source.tool === "tally") {
        const snapshot = await discoverClientContext(plan.config.tally, {
          onProgress: (company, status, progress) => {
            currentProgress = progress;
            return onProgress(source.key, status, company, progress);
          },
        });
        sources.push({ ...source, status: "ready", snapshot });
        delete sources.at(-1).label;
      } else if (source.tool === "excel") {
        const files = await inventory(folderFor(source.key));
        const selected = files.filter((f) => /\.xlsx$/i.test(f.path));
        const size = selected.reduce(
          (n, f) => n + Buffer.from(f.content, "base64").length,
          0,
        );
        if (
          selectedBytes + size > 8_000_000 ||
          selectedFiles + selected.length > 45
        ) {
          sources.push({
            key: source.key,
            tool: "excel",
            status: "unavailable",
            error:
              "This folder exceeds the selected run limit of 45 workbooks and 8 MB. Connect a smaller folder and refresh.",
          });
          await onProgress(source.key, "unavailable");
          continue;
        }
        selectedBytes += size;
        selectedFiles += selected.length;
        const workbooks = [];
        for (const file of files.filter((f) => /\.xlsx$/i.test(f.path))) {
          const progress = (activity) => {
            currentProgress = { completed: workbooks.filter(book => book.status === "ready").length,
              total: selected.length, activity, item: file.path };
            return onProgress(source.key, "reading", null, currentProgress);
          };
          await progress("Reading workbook");
          let bytes = Buffer.from(file.content, "base64");
          bytes = await excelSchemaBytes(bytes);
          selected.find((s) => s.path === file.path).content = bytes.toString("base64");
          const book = {
            path: file.path,
            sha256: createHash("sha256").update(bytes).digest("hex"),
          };
          try {
            workbooks.push({
              ...book,
              status: "ready",
              structure: await inspectExcel(bytes),
            });
          } catch {
            workbooks.push({
              ...book,
              status: "unavailable",
              error:
                "Could not inspect this workbook. Check that it is a supported .xlsx file and refresh.",
            });
          }
          await progress(workbooks.at(-1).status === "ready" ? "Collected workbook" : "Workbook needs attention");
        }
        if (!workbooks.length) throw new Error("No workbooks");
        sources.push({
          key: source.key,
          tool: "excel",
          status: "ready",
          files: selected,
          workbooks,
        });
      } else throw new Error("Unsupported source");
    } catch (error) {
      if (error.code === "TASK_STOPPED") throw error;
      sources.push({
        key: source.key,
        tool: source.tool,
        status: "unavailable",
        error:
          error.tallyScope ? error.message : source.tool === "tally"
            ? "Tally service or company access could not be verified. Check Tally on this PC and retry discovery."
            : "Folder is unavailable. Reconnect the original folder on this PC and refresh.",
      });
    }
    await onProgress(source.key, sources.at(-1).status, null, currentProgress);
  }
  return { sources };
}
