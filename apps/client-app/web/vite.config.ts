import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@/*": path.resolve(__dirname, "src"),
      // Monorepo shared brand tokens — edit shared/brand/ to affect all apps
      "@minkops/brand": path.resolve(__dirname, "../../../shared/brand")
    }
  },
  server: {
    port: 3000,
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
