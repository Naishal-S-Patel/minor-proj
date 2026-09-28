import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxies /api/* requests to the FastAPI backend during local dev.
    // Why this matters: without it, the frontend (localhost:5173) calling
    // the backend (localhost:8000) is a cross-origin request, which means
    // every fetch depends on CORS being configured exactly right, and any
    // httpOnly auth cookies (planned for Phase 4) behave differently
    // cross-origin than same-origin. Proxying makes local dev behave like
    // production, where the frontend and API are typically served through
    // the same origin (or a reverse proxy) rather than two different ports.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
