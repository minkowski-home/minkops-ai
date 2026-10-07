/** Run a bounded collection plan. One unavailable source never hides others. */
import { createHash } from "node:crypto";

export async function collectSources(
  plan,
  { folderFor, inventory, inspectExcel, discoverTally, excelSchemaBytes, onProgress },
) {
  const sources = [];
  let selectedBytes = 0,
    selectedFiles = 0;
  for (const source of plan.sources) {
    await onProgress(source.key, "reading");
    try {
      if (source.tool === "tally") {
        const snapshot = await discoverTally(
          { ...plan.config.tally, depth: plan.config.depth },
          {
            onProgress: (category, status) =>
              onProgress(source.key, status, category),
          },
        );
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
          let bytes = Buffer.from(file.content, "base64");
          if (plan.config.depth === "structure") {
            bytes = await excelSchemaBytes(bytes);
            selected.find((s) => s.path === file.path).content = bytes.toString("base64");
          }
          const book = {
            path: file.path,
            sha256: createHash("sha256").update(bytes).digest("hex"),
          };
          try {
            workbooks.push({
              ...book,
              status: "ready",
              structure: await inspectExcel(bytes, plan.config.depth),
            });
          } catch {
            workbooks.push({
              ...book,
              status: "unavailable",
              error:
                "Could not inspect this workbook. Check that it is a supported .xlsx file and refresh.",
            });
          }
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
    } catch {
      sources.push({
        key: source.key,
        tool: source.tool,
        status: "unavailable",
        error:
          source.tool === "tally"
            ? "Tally is unavailable or the selected company is not open. Open Tally and refresh."
            : "Folder is unavailable. Reconnect the original folder on this PC and refresh.",
      });
    }
    await onProgress(source.key, sources.at(-1).status);
  }
  return { sources };
}
