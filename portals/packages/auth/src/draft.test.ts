import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { DraftStore, sanitizeDraft } from "./draft";
import { securityMiddleware, storageOrigin } from "./security-headers";
import type { KeyValue } from "./session";

class ExpiringKV implements KeyValue {
  data = new Map<string, { value: string; until: number }>();
  now = 0;
  async get(k: string) {
    const e = this.data.get(k);
    return e && e.until > this.now ? e.value : null;
  }
  async set(k: string, v: string, _mode: "EX", seconds: number) { this.data.set(k, { value: v, until: this.now + seconds }); return "OK"; }
  async expire() { return 1; }
  async del(k: string) { this.data.delete(k); return 1; }
}

describe("estimator draft (ADR-0014: amounts never in the URL)", () => {
  it("keeps the amount and term server-side until it expires", async () => {
    const kv = new ExpiringKV();
    const drafts = new DraftStore(kv, 1800);
    const id = await drafts.save({ amount: 55_000_000, term: 12 });
    expect(id).toMatch(/^[A-Za-z0-9_-]{40,}$/);
    expect(await drafts.get(id)).toEqual({ amount: 55_000_000, term: 12 });
    kv.now += 1801;
    expect(await drafts.get(id)).toBeNull();
  });

  it("reuses the cookie's id and forgets the draft after submission", async () => {
    const drafts = new DraftStore(new ExpiringKV());
    const id = await drafts.save({ amount: 10_000_000, term: 6 });
    expect(await drafts.save({ amount: 20_000_000, term: 6 }, id)).toBe(id);
    await drafts.clear(id);
    expect(await drafts.get(id)).toBeNull();
  });

  it("never trusts the stored values", () => {
    expect(sanitizeDraft({ amount: 1, term: 99 })).toEqual({ amount: 40_000_000, term: 24 });
    expect(sanitizeDraft({ amount: 40_500_000, term: 24 }).amount).toBe(40_000_000);
    expect(sanitizeDraft({ amount: 30_000_000, term: 18, flash: "<script>" })).toEqual({ amount: 30_000_000, term: 18 });
    expect(sanitizeDraft({ amount: 30_000_000, term: 18, flash: "exists" }).flash).toBe("exists");
  });

  it("ignores a forged cookie id", async () => {
    const drafts = new DraftStore(new ExpiringKV());
    expect(await drafts.save({ amount: 10_000_000, term: 6 }, "../../sess:abc")).not.toContain("sess");
  });
});

describe("document uploads in the CSP", () => {
  afterEach(() => vi.unstubAllEnvs());
  const request = () => new NextRequest(new URL("/apply", "http://localhost:3001"), { headers: { cookie: "__Host-session=a" } });

  it("allows exactly the storage origin for connect-src", () => {
    vi.stubEnv("STORAGE_PUBLIC_ORIGIN", "http://localhost:9000");
    const csp = securityMiddleware(request(), []).headers.get("content-security-policy");
    expect(csp).toContain("connect-src 'self' http://localhost:9000;");
  });

  it("drops anything that is not a bare origin", () => {
    expect(storageOrigin("http://localhost:9000/")).toBe("http://localhost:9000");
    expect(storageOrigin("https://docs.credit.local/loan-documents")).toBeNull();
    expect(storageOrigin("javascript:alert(1)")).toBeNull();
    expect(storageOrigin("* data:")).toBeNull();
    expect(storageOrigin(undefined)).toBeNull();
  });

  it("keeps connect-src to self without a storage origin", () => {
    vi.stubEnv("STORAGE_PUBLIC_ORIGIN", "");
    expect(securityMiddleware(request(), []).headers.get("content-security-policy")).toContain("connect-src 'self';");
  });
});
