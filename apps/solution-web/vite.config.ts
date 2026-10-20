import path from "path";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const ROOT_DIRECTORY = path.resolve(__dirname, "../..");

/** Serve (dev) and emit (build) the favicon at its stable /favicon.svg URL from
 * design/, the only home of brand assets. */
function favicon(source: string): Plugin {
  return {
    name: "minkops-favicon",
    configureServer(server) {
      server.middlewares.use("/favicon.svg", (_request, response) => {
        response.setHeader("Content-Type", "image/svg+xml");
        response.end(readFileSync(source));
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "favicon.svg", source: readFileSync(source) });
    },
  };
}

export default defineConfig(({ mode, command }) => {
  const environment = loadEnv(mode, process.cwd(), "");
  const apiTarget = environment.VITE_API_TARGET ?? "http://127.0.0.1:8000";
  const buildId = command === 'build' ? randomUUID() : 'development';

  return {
    plugins: [react(), favicon(path.join(ROOT_DIRECTORY, "design/assets/logos/favicon-console.svg")), { name: 'console-version', generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ id: buildId }) });
    } }],
    define: { __MINKOPS_BUILD_ID__: JSON.stringify(buildId) },
    resolve: {
      alias: {
        "@/*": path.resolve(__dirname, "src"),
        "@minkops/design": path.join(ROOT_DIRECTORY, "design"),
        "@minkops/solution-contracts": path.join(ROOT_DIRECTORY, "packages/solution-contracts/src"),
        // Solution UI files are intentionally outside this app root. Resolve the
        // host-owned React dependencies here so every solution shares one runtime.
        react: path.resolve(__dirname, "node_modules/react"),
        "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
        "react-router-dom": path.resolve(__dirname, "node_modules/react-router-dom")
      }
    },
    server: {
      port: 3000,
      fs: {
        allow: [ROOT_DIRECTORY]
      },
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true
        }
      }
    },
    preview: {
      port: 3001
    },
  };
});
