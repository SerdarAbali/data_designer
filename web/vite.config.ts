import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    proxy: {
      "/health": "http://api:8000",
      "/api": "http://api:8000",
    },
  },
});
