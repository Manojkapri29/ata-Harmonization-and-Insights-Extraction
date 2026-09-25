import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The UI calls /api/*; in development Vite forwards those requests to the FastAPI backend.
const backend = process.env.JOBPILOT_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: { "/api": { target: backend, changeOrigin: true } },
  },
  preview: { port: 4173, proxy: { "/api": { target: backend, changeOrigin: true } } },
});
