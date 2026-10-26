import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {rollupOptions: {output: {manualChunks: {charts:["recharts"], forms:["react-hook-form","zod","@hookform/resolvers/zod"]}}}},
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
