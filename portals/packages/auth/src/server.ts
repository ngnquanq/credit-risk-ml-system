import { Redis } from "ioredis";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { loadConfig, type PortalConfig, type Realm } from "./config";
import { verifyMutation, CSRF_FIELD } from "./csrf";
import { DraftStore, type LoanDraft } from "./draft";
import { refreshIfNeeded } from "./oidc";
import { DRAFT_COOKIE, SESSION_COOKIE, SessionStore, type Session } from "./session";

let cached: { config: PortalConfig; store: SessionStore; drafts: DraftStore } | null = null;

export function portal(realm: Realm): { config: PortalConfig; store: SessionStore; drafts: DraftStore } {
  if (!cached) {
    const config = loadConfig(realm);
    const kv = new Redis(config.redisUrl, { lazyConnect: false, maxRetriesPerRequest: 2 });
    cached = {
      config,
      store: new SessionStore(kv, config.idleTimeout, config.absoluteTimeout),
      drafts: new DraftStore(kv),
    };
  }
  return cached;
}

export const sessionCookieOptions = {
  httpOnly: true,
  secure: true,
  sameSite: "lax" as const,
  path: "/",
};

/** The current session or null, without redirecting (layouts, error pages). */
export async function optionalSession(realm: Realm): Promise<Session | null> {
  const { store } = portal(realm);
  return store.get(cookies().get(SESSION_COOKIE)?.value);
}

/** For server components and server actions. Redirects to sign-in, or to /forbidden when no role matches. */
export async function requireSession(realm: Realm, roles?: string[]): Promise<Session> {
  const { config, store } = portal(realm);
  const id = cookies().get(SESSION_COOKIE)?.value;
  const current = await store.get(id);
  const session = current && id ? await refreshIfNeeded(config, store, id, current) : null;
  if (!session) {
    const path = headers().get("x-pathname") ?? "/";
    redirect(`/auth/login?returnTo=${encodeURIComponent(path)}`);
  }
  if (roles && !roles.some((r) => session.roles.includes(r))) redirect("/forbidden");
  return session;
}

/** Server actions called from client components (no form, so no CSRF field): Origin must be ours. */
export function assertSameOrigin(realm: Realm): void {
  const { config } = portal(realm);
  if (headers().get("origin") !== config.baseUrl) throw new Error("Request rejected: foreign origin");
}

/** Estimator draft behind an httpOnly cookie (ADR-0014: amounts stay out of URLs). */
export async function saveLoanDraft(realm: Realm, draft: LoanDraft): Promise<void> {
  const { drafts } = portal(realm);
  const id = await drafts.save(draft, cookies().get(DRAFT_COOKIE)?.value);
  cookies().set(DRAFT_COOKIE, id, { ...sessionCookieOptions, maxAge: 1800 });
}

/** Read (and consume the flash message of) the draft; null when there is none. */
export async function readLoanDraft(realm: Realm): Promise<LoanDraft | null> {
  const { drafts } = portal(realm);
  const id = cookies().get(DRAFT_COOKIE)?.value;
  const draft = await drafts.get(id);
  if (draft?.flash && id) await drafts.save({ amount: draft.amount, term: draft.term }, id);
  return draft;
}

/** After a successful submission. Server actions and route handlers only (cookies are read-only in pages). */
export async function clearLoanDraft(realm: Realm): Promise<void> {
  const { drafts } = portal(realm);
  await drafts.clear(cookies().get(DRAFT_COOKIE)?.value);
  cookies().delete(DRAFT_COOKIE);
}

/** Server actions call this first: CSRF token plus Origin check (E12 AC2). */
export function assertMutation(realm: Realm, session: Session, form: FormData): void {
  const { config } = portal(realm);
  if (!verifyMutation(session, form.get(CSRF_FIELD), headers().get("origin"), config.baseUrl)) {
    throw new Error("Request rejected: invalid CSRF token or origin");
  }
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly body: unknown) {
    super(`API responded ${status}`);
  }
}

/** Calls the Loan API with the user's access token (token relay). Never exposes the token to the browser. */
export async function api<T>(realm: Realm, session: Session, path: string, init: RequestInit = {}): Promise<T> {
  const { config } = portal(realm);
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${session.accessToken}`,
      "Content-Type": "application/json",
      // Reasons come back in the portal's language (the API reads Accept-Language, not the URL).
      "Accept-Language": realm === "customers" ? "vi" : "en",
    },
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
