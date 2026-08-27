/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vite plugin that injects a version tag for cache-busting on reloads.

// Backend base for the dev proxy. Production uses `/api` same-origin (behind a
// reverse proxy/CDN), so only local development needs the port.
const BACKEND_TARGET = "http://localhost:8000";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Keep auth (HttpOnly cookies) + JSON APIs same-origin during dev so the
      // cookie path flows exactly like production and CSRF origin checks pass.
      "/api": {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "es2020",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // Group heavy 3D + animation deps into their own lazily-loaded chunks.
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("three")) return "three";
            if (id.includes("gsap")) return "animations";
            return "vendor";
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/testing/setup.ts",
    css: false,
  },
});