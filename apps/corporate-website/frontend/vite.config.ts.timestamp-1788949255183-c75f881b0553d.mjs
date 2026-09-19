// vite.config.ts
import path from "path";
import { defineConfig } from "file:///sessions/rcw-0128uprweprjhm99tanpqzqt/mnt/minkops-ai/apps/corporate-website/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///sessions/rcw-0128uprweprjhm99tanpqzqt/mnt/minkops-ai/apps/corporate-website/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
var __vite_injected_original_dirname = "/sessions/rcw-0128uprweprjhm99tanpqzqt/mnt/minkops-ai/apps/corporate-website/frontend";
var API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:5000";
var vite_config_default = defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@/*": path.resolve(__vite_injected_original_dirname, "src"),
      // Monorepo shared brand tokens — edit shared/brand/ to affect all apps
      "@minkops/brand": path.resolve(__vite_injected_original_dirname, "../../../shared/brand")
    }
  },
  server: {
    port: 5173,
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
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvcmN3LTAxMjh1cHJ3ZXByamhtOTl0YW5wcXpxdC9tbnQvbWlua29wcy1haS9hcHBzL2NvcnBvcmF0ZS13ZWJzaXRlL2Zyb250ZW5kXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvc2Vzc2lvbnMvcmN3LTAxMjh1cHJ3ZXByamhtOTl0YW5wcXpxdC9tbnQvbWlua29wcy1haS9hcHBzL2NvcnBvcmF0ZS13ZWJzaXRlL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9zZXNzaW9ucy9yY3ctMDEyOHVwcndlcHJqaG05OXRhbnBxenF0L21udC9taW5rb3BzLWFpL2FwcHMvY29ycG9yYXRlLXdlYnNpdGUvZnJvbnRlbmQvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgcGF0aCBmcm9tIFwicGF0aFwiO1xuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSBcInZpdGVcIjtcbmltcG9ydCByZWFjdCBmcm9tIFwiQHZpdGVqcy9wbHVnaW4tcmVhY3RcIjtcblxuY29uc3QgQVBJX1RBUkdFVCA9IHByb2Nlc3MuZW52LlZJVEVfQVBJX1RBUkdFVCA/PyBcImh0dHA6Ly8xMjcuMC4wLjE6NTAwMFwiO1xuXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuICBwbHVnaW5zOiBbcmVhY3QoKV0sXG4gIHJlc29sdmU6IHtcbiAgICBhbGlhczoge1xuICAgICAgXCJALypcIjogcGF0aC5yZXNvbHZlKF9fZGlybmFtZSwgXCJzcmNcIiksXG4gICAgICAvLyBNb25vcmVwbyBzaGFyZWQgYnJhbmQgdG9rZW5zIFx1MjAxNCBlZGl0IHNoYXJlZC9icmFuZC8gdG8gYWZmZWN0IGFsbCBhcHBzXG4gICAgICBcIkBtaW5rb3BzL2JyYW5kXCI6IHBhdGgucmVzb2x2ZShfX2Rpcm5hbWUsIFwiLi4vLi4vLi4vc2hhcmVkL2JyYW5kXCIpXG4gICAgfVxuICB9LFxuICBzZXJ2ZXI6IHtcbiAgICBwb3J0OiA1MTczLFxuICAgIHByb3h5OiB7XG4gICAgICBcIi9hcGlcIjoge1xuICAgICAgICB0YXJnZXQ6IEFQSV9UQVJHRVQsXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZVxuICAgICAgfVxuICAgIH1cbiAgfSxcbiAgcHJldmlldzoge1xuICAgIHBvcnQ6IDQxNzNcbiAgfVxufSk7XG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQWliLE9BQU8sVUFBVTtBQUNsYyxTQUFTLG9CQUFvQjtBQUM3QixPQUFPLFdBQVc7QUFGbEIsSUFBTSxtQ0FBbUM7QUFJekMsSUFBTSxhQUFhLFFBQVEsSUFBSSxtQkFBbUI7QUFFbEQsSUFBTyxzQkFBUSxhQUFhO0FBQUEsRUFDMUIsU0FBUyxDQUFDLE1BQU0sQ0FBQztBQUFBLEVBQ2pCLFNBQVM7QUFBQSxJQUNQLE9BQU87QUFBQSxNQUNMLE9BQU8sS0FBSyxRQUFRLGtDQUFXLEtBQUs7QUFBQTtBQUFBLE1BRXBDLGtCQUFrQixLQUFLLFFBQVEsa0NBQVcsdUJBQXVCO0FBQUEsSUFDbkU7QUFBQSxFQUNGO0FBQUEsRUFDQSxRQUFRO0FBQUEsSUFDTixNQUFNO0FBQUEsSUFDTixPQUFPO0FBQUEsTUFDTCxRQUFRO0FBQUEsUUFDTixRQUFRO0FBQUEsUUFDUixjQUFjO0FBQUEsTUFDaEI7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsTUFBTTtBQUFBLEVBQ1I7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
