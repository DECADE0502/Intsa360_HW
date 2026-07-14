import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./src/test/e2e",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command:
          process.env.PLAYWRIGHT_WEB_SERVER_COMMAND ?? "npm run dev -- --host 127.0.0.1 --port 4173",
        reuseExistingServer: !process.env.CI,
        url: baseURL,
      },
});
