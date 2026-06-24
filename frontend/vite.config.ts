import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the backend so the SPA and API share an origin
// locally (and CSP connect-src 'self' just works in dev).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
