import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    // Allow Tailscale MagicDNS names (e.g. pihost.tail8abbac.ts.net) so the
    // dev server can be reached remotely via `tailscale serve`. Plain HTTP
    // from LAN IP addresses was already permitted by Vite.
    allowedHosts: [".ts.net"],
    proxy: {
      "/health": "http://api:8000",
      "/api": "http://api:8000",
    },
  },
});
