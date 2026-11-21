import { defineConfig, devices } from "@playwright/test";

// Runs against UAT (E16). One test user per role from scripts/uat/create_test_users.sh.
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.E2E_BASE_URL ?? "https://staff.credit.local", ignoreHTTPSErrors: true },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }],
});
