import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const USER = process.env.E2E_APPLICANT_USER ?? "";
const PASSWORD = process.env.E2E_APPLICANT_PASSWORD ?? "";
const OTHER_APPLICATION = process.env.E2E_OTHER_APPLICATION_ID ?? "B1";

async function signIn(page: Page) {
  await page.goto("/auth/login");
  await page.getByLabel(/email|username/i).fill(USER);
  await page.getByLabel(/password|mật khẩu/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in|đăng nhập/i }).click();
  await page.waitForURL((url) => !url.hostname.startsWith("auth."));
}

test("security headers are present (E12 AC5)", async ({ request }) => {
  const response = await request.get("/");
  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["strict-transport-security"]).toBeTruthy();
  expect(headers["referrer-policy"]).toBe("no-referrer");
});

test("no token is reachable from browser JavaScript (E12 AC1)", async ({ page }) => {
  test.skip(!USER, "E2E_APPLICANT_USER not set");
  await signIn(page);
  const exposed = await page.evaluate(() => {
    const values = [document.cookie, document.documentElement.outerHTML];
    for (const store of [localStorage, sessionStorage]) {
      for (let i = 0; i < store.length; i++) values.push(store.getItem(store.key(i) ?? "") ?? "");
    }
    return values.some((v) => /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./.test(v));
  });
  expect(exposed).toBe(false);
});

test("another applicant's file looks like a missing one (E12 AC4)", async ({ page }) => {
  test.skip(!USER, "E2E_APPLICANT_USER not set");
  await signIn(page);
  const response = await page.goto(`/applications/${OTHER_APPLICATION}`);
  expect(response?.status()).toBe(404);
});

test("estimator has no serious accessibility violations (E12 AC7)", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});
