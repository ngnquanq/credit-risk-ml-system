import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { loadConfig } from "./config";
import { securityMiddleware } from "./security-headers";

const base = {
  OIDC_ISSUER: "http://localhost:8180/realms/staff",
  OIDC_CLIENT_ID: "staff-portal",
  OIDC_CLIENT_SECRET: "test-secret",
  PORTAL_BASE_URL: "http://localhost:3002",
  SESSION_REDIS_URL: "redis://localhost:6380/1",
  API_BASE_URL: "http://localhost:8000",
};

function withEnv(env: Record<string, string>) {
  for (const [k, v] of Object.entries({ ...base, ...env })) vi.stubEnv(k, v);
}

afterEach(() => vi.unstubAllEnvs());

describe("plain-http issuer (local stack only)", () => {
  it("is allowed in development when explicitly requested", () => {
    withEnv({ NODE_ENV: "development", OIDC_ALLOW_INSECURE_HTTP: "true" });
    expect(loadConfig("staff").allowInsecureHttp).toBe(true);
  });

  it("is never allowed in production, even when requested", () => {
    withEnv({ NODE_ENV: "production", OIDC_ALLOW_INSECURE_HTTP: "true" });
    expect(loadConfig("staff").allowInsecureHttp).toBe(false);
  });

  it("is off by default", () => {
    withEnv({ NODE_ENV: "development" });
    expect(loadConfig("staff").allowInsecureHttp).toBe(false);
  });
});

describe("security middleware", () => {
  const request = (path: string, cookie?: string) =>
    new NextRequest(new URL(path, "http://localhost:3002"), cookie ? { headers: { cookie } } : undefined);

  it("sends a strict CSP and security headers", () => {
    withEnv({ NODE_ENV: "production" });
    const response = securityMiddleware(request("/reviews", "__Host-session=abc"), []);
    const csp = response.headers.get("content-security-policy") ?? "";
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    expect(csp).not.toContain("unsafe-eval");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
  });

  it("only relaxes eval for the dev server", () => {
    withEnv({ NODE_ENV: "development" });
    const csp = securityMiddleware(request("/reviews", "__Host-session=abc"), []).headers.get("content-security-policy");
    expect(csp).toContain("'unsafe-eval'");
  });

  it("uses a fresh nonce per request", () => {
    withEnv({ NODE_ENV: "production" });
    const nonce = (r: Response) => /nonce-([^']+)/.exec(r.headers.get("content-security-policy") ?? "")?.[1];
    const a = securityMiddleware(request("/reviews", "__Host-session=abc"), []);
    const b = securityMiddleware(request("/reviews", "__Host-session=abc"), []);
    expect(nonce(a)).toBeTruthy();
    expect(nonce(a)).not.toBe(nonce(b));
  });

  it("redirects to sign-in without a session cookie, keeping the path", () => {
    const response = securityMiddleware(request("/cases/100002"), ["/forbidden"]);
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3002/auth/login?returnTo=%2Fcases%2F100002");
  });

  it("lets public paths and auth routes through without a session", () => {
    expect(securityMiddleware(request("/forbidden"), ["/forbidden"]).status).toBe(200);
    expect(securityMiddleware(request("/auth/callback?code=x"), []).status).toBe(200);
  });
});
