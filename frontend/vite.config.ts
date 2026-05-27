import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/config": backend,
      "/health": backend,
      "/progress": backend,
      "/progress-report": backend,
    },
  },
});
