import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          motion: ["framer-motion"],
        },
      },
    },
  },
  server: { host: "127.0.0.1", proxy: { "/api": process.env.SHIPMENT_API_ORIGIN || "http://127.0.0.1:8000" } },
  test: {
    include: ["src/**/*.test.tsx"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
