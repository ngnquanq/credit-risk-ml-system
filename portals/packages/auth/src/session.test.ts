import { describe, expect, it } from "vitest";
import { verifyMutation } from "./csrf";
import { safeReturnTo } from "./oidc";
import { SessionStore, type KeyValue } from "./session";

class MapKV implements KeyValue {
  data = new Map<string, string>();
  async get(k: string) { return this.data.get(k) ?? null; }
  async set(k: string, v: string) { this.data.set(k, v); return "OK"; }
  async expire() { return 1; }
  async del(k: string) { this.data.delete(k); return 1; }
}

const base = { sub: "u1", roles: ["applicant"], accessToken: "at", expiresAt: 0 };

describe("SessionStore", () => {
  it("ends the session after the absolute timeout", async () => {
    let now = 1000;
    const store = new SessionStore(new MapKV(), 1800, 28800, () => now);
    const { id } = await store.create(base);
    expect(await store.get(id)).not.toBeNull();
    now += 28801;
    expect(await store.get(id)).toBeNull();
  });

  it("lets a login state be used once", async () => {
    const store = new SessionStore(new MapKV(), 1800, 28800);
    await store.savePendingLogin("s1", { codeVerifier: "v", nonce: "n", returnTo: "/" });
    expect(await store.takePendingLogin("s1")).not.toBeNull();
    expect(await store.takePendingLogin("s1")).toBeNull();
  });
});

describe("CSRF and redirects", () => {
  it("rejects a foreign origin or a wrong token", async () => {
    const store = new SessionStore(new MapKV(), 1800, 28800);
    const { session } = await store.create(base);
    const origin = "https://apply.credit.local";
    expect(verifyMutation(session, session.csrfToken, origin, origin)).toBe(true);
    expect(verifyMutation(session, session.csrfToken, "https://evil.test", origin)).toBe(false);
    expect(verifyMutation(session, "wrong", origin, origin)).toBe(false);
    expect(verifyMutation(session, null, origin, origin)).toBe(false);
  });

  it("only allows same-origin relative return paths", () => {
    expect(safeReturnTo("/applications/1")).toBe("/applications/1");
    expect(safeReturnTo("https://evil.test")).toBe("/");
    expect(safeReturnTo("//evil.test")).toBe("/");
    expect(safeReturnTo("/\\evil.test")).toBe("/");
  });
});
