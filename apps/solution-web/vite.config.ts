import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@/*": path.resolve(__dirname, "src"),
      // Repo-owned console tokens and primitives; the desktop shell can reuse this UI.
      "@minkops/design": path.resolve(__dirname, "../../design"),
      "@minkops/solution-contracts": path.resolve(__dirname, "../../packages/solution-contracts/src")
    }
  },
  server: {
    port: 3000,
    fs: {
      allow: [path.resolve(__dirname, "../..")]
    },
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true
      }
    }
  },
  preview: {
    port: 3001
  }
});
