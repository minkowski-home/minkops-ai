import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:5000";
// design/ is the single source of the brand kit (tokens, logos, icons).
const DESIGN_DIRECTORY = path.resolve(__dirname, "../../../design");

export default defineConfig({
  plugins: [react()],
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
