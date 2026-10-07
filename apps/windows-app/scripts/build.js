import { build } from "esbuild";
import { mkdir, readFile, writeFile, cp } from "node:fs/promises";
await build({
  entryPoints: ["src/main.js"],
  outfile: "dist/main.cjs",
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
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
