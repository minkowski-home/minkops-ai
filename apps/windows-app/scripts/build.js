import { build } from "esbuild";
import { mkdir, readFile, writeFile, cp } from "node:fs/promises";
import { resolve } from "node:path";
await build({
  entryPoints: ["src/main.js"],
  outfile: "dist/main.cjs",
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
  // npm file dependencies can be copies on Windows. Bundle the current workspace
  // sources, while resolving third-party dependencies from this app's lockfile.
  alias: {
    "@minkops/desktop-connectors": resolve("../../connectors/desktop/src/index.js"),
    "@minkops/desktop-runtime": resolve("../../platform/desktop-runtime/src/worker.js"),
    "@minkops/desktop-runtime/jobs": resolve("../../platform/desktop-runtime/src/jobs.js"),
  },
  nodePaths: [resolve("node_modules")],
});
await build({
  entryPoints: ["src/preload.js"],
  outfile: "dist/preload.cjs",
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});
// Ship compiled runtime code, without development tools or workspace symlinks.
const metadata = JSON.parse(await readFile("package.json", "utf8"));
await mkdir("bundle", { recursive: true });
await cp("dist", "bundle/dist", { recursive: true });
await cp("assets", "bundle/assets", { recursive: true });
const { name, version, description, author, main } = metadata;
await writeFile(
  "bundle/package.json",
  JSON.stringify({ name, version, description, author, main }, null, 2),
);
