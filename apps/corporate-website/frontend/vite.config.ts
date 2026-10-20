import path from "path";
import { readFileSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:5000";
// design/ is the single source of the brand kit (tokens, logos, icons).
const DESIGN_DIRECTORY = path.resolve(__dirname, "../../../design");

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

export default defineConfig({
  plugins: [react(), favicon(path.join(DESIGN_DIRECTORY, "assets/logos/favicon-website.svg"))],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@minkops/design": DESIGN_DIRECTORY
    }
  },
  server: {
    port: 5173,
    fs: {
      allow: [__dirname, DESIGN_DIRECTORY]
    },
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true
      }
    }
  },
  preview: {
    port: 4173
  }
});
