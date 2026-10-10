/** Test bridge to actual Windows adapters; never reads model credentials. */
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import {
  discoverTally,
  discoverClientContext,
  excelSchemaBytes,
  saveDiscoveryPackage,
  readTallyBills,
  inspectExcel,
  commitTallyBill,
  inventory,
  replaceApproved,
} from "../connectors/desktop/src/index.js";
import { collectSources } from "../platform/desktop-runtime/src/discovery.js";
const chunks = [];
for await (const part of process.stdin) chunks.push(part);
const input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
let result;
if (input.operation === "discover") result = await discoverTally(input.config);
else if (input.operation === "client_context") result = await discoverClientContext(input.config);
else if (input.operation === "archive") result = await saveDiscoveryPackage(input.root, input.catalog);
else if (input.operation === "read") result = await readTallyBills(input.plan);
else if (input.operation === "read_file") result = { content: (await readFile(input.path)).toString("base64") };
else if (input.operation === "schema") {
  const content = await excelSchemaBytes(await readFile(input.path));
  result = { content: content.toString("base64"), structure: await inspectExcel(content, "structure") };
}
else if (input.operation === "inspect")
  result = await inspectExcel(await readFile(input.path));
else if (input.operation === "refresh") result = { files: await inventory(input.root) };
else if (input.operation === "save") result = await commitTallyBill(input.plan);
else if (input.operation === "collect")
  result = await collectSources(input.plan, {
    folderFor: () => input.root,
    inventory,
    inspectExcel,
    discoverTally,
    discoverClientContext,
    excelSchemaBytes,
    onProgress: async () => {},
  });
else if (input.operation === "save_excel") {
  const bytes = await replaceApproved(
    input.root,
    input.plan,
    Buffer.from(input.plan.content, "base64"),
    (previous) =>
      writeFile(join(input.root, ".min119-proof-backup.xlsx"), previous),
  );
  result = { content: bytes.toString("base64") };
} else throw new Error("Unsupported test operation.");
process.stdout.write(JSON.stringify(result));
