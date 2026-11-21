import { defineConfig, devices } from "@playwright/test";

// Runs against UAT (E16). Test users come from scripts/uat/create_test_users.sh.
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.E2E_BASE_URL ?? "https://apply.credit.local", ignoreHTTPSErrors: true },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
});
