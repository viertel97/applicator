import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  webServer: {
    // Dedicated port + strictPort so the suite always spins up *this* app's
    // dev server. Without it, a stray vite on the default 5173 gets reused and
    // the specs silently run against the wrong app.
    command: "node node_modules/.bin/vite --port 5274 --strictPort",
    port: 5274,
    reuseExistingServer: false,
  },
  use: { baseURL: "http://localhost:5274" },
});
