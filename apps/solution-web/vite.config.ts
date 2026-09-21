import { existsSync } from "fs";
import path from "path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const ROOT_DIRECTORY = path.resolve(__dirname, "../..");

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, process.cwd(), "");
  const solutionId = environment.VITE_SOLUTION ?? "mock-client";
  if (!/^[a-z0-9-]+$/.test(solutionId)) {
    throw new Error("VITE_SOLUTION must be a lowercase, hyphenated solution identifier.");
  }

  const requestedEntry = path.join(ROOT_DIRECTORY, "solutions", solutionId, "web", "src", "App.tsx");
  const solutionManifest = path.join(ROOT_DIRECTORY, "solutions", solutionId, "solution.ts");
  if (!existsSync(solutionManifest)) {
    throw new Error(`No solution manifest found for "${solutionId}".`);
  }
  const solutionEntry = existsSync(requestedEntry)
    ? requestedEntry
    : path.resolve(__dirname, "src/starter/App.tsx");
  const apiTarget = environment.VITE_API_TARGET ?? "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@/*": path.resolve(__dirname, "src"),
        "@minkops/design": path.join(ROOT_DIRECTORY, "design"),
        "@minkops/solution-contracts": path.join(ROOT_DIRECTORY, "packages/solution-contracts/src"),
        "@minkops/solution-entry": solutionEntry,
        "@minkops/solution-manifest": solutionManifest,
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
