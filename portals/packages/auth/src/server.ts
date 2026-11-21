import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { loadConfig, type PortalConfig, type Realm } from "./config";
import { verifyMutation, CSRF_FIELD } from "./csrf";
import { refreshIfNeeded } from "./oidc";
import { SESSION_COOKIE, SessionStore, type Session } from "./session";

let cached: { config: PortalConfig; store: SessionStore } | null = null;

export function portal(realm: Realm): { config: PortalConfig; store: SessionStore } {
  if (!cached) {
    const config = loadConfig(realm);
    cached = { config, store: SessionStore.fromUrl(config.redisUrl, config.idleTimeout, config.absoluteTimeout) };
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
    },
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
