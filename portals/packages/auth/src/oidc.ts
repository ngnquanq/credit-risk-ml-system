import * as client from "openid-client";
import type { PortalConfig } from "./config";
import { randomToken, type Session, type SessionStore } from "./session";

const REFRESH_MARGIN_SECONDS = 30;
let configuration: Promise<client.Configuration> | null = null;

function oidc(config: PortalConfig): Promise<client.Configuration> {
  // Plain-http issuers are refused unless explicitly allowed; only the local stack (scripts/local) sets this.
  const insecure = config.allowInsecureHttp && config.issuer.startsWith("http://");
  configuration ??= client.discovery(
    new URL(config.issuer),
    config.clientId,
    config.clientSecret,
    undefined,
    insecure ? { execute: [client.allowInsecureRequests] } : undefined,
  );
  return configuration;
}

function rolesFrom(claims: Record<string, unknown>): string[] {
  const realmAccess = claims["realm_access"] as { roles?: string[] } | undefined;
  return realmAccess?.roles ?? [];
}

function decodePayload(jwt: string): Record<string, unknown> {
  const part = jwt.split(".")[1] ?? "";
  return JSON.parse(Buffer.from(part, "base64url").toString("utf8")) as Record<string, unknown>;
}

/** Only same-origin relative paths may be used after sign-in (no open redirects). */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/";
  return value;
}

export async function startLogin(config: PortalConfig, store: SessionStore, returnTo: string): Promise<URL> {
  const codeVerifier = client.randomPKCECodeVerifier();
  const state = randomToken();
  const nonce = randomToken();
  await store.savePendingLogin(state, { codeVerifier, nonce, returnTo: safeReturnTo(returnTo) });
  return client.buildAuthorizationUrl(await oidc(config), {
    redirect_uri: `${config.baseUrl}/auth/callback`,
    scope: "openid profile email",
    code_challenge: await client.calculatePKCECodeChallenge(codeVerifier),
    code_challenge_method: "S256",
    state,
    nonce,
  });
}

export async function completeLogin(
  config: PortalConfig,
  store: SessionStore,
  callbackUrl: URL,
): Promise<{ id: string; returnTo: string }> {
  const state = callbackUrl.searchParams.get("state");
  const pending = state ? await store.takePendingLogin(state) : null;
  if (!state || !pending) throw new Error("Unknown or expired login state");

  const tokens = await client.authorizationCodeGrant(await oidc(config), callbackUrl, {
    pkceCodeVerifier: pending.codeVerifier,
    expectedState: state,
    expectedNonce: pending.nonce,
  });
  // scope includes "openid", so a valid response always carries an ID token.
  const claims = tokens.claims();
  if (!claims) throw new Error("Token response has no ID token");
  const access = decodePayload(tokens.access_token);
  const { id } = await store.create({
    sub: claims.sub,
    name: typeof claims.name === "string" ? claims.name : undefined,
    roles: rolesFrom(access),
    branchId: typeof access["branch_id"] === "string" ? (access["branch_id"] as string) : null,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
    expiresAt: Math.floor(Date.now() / 1000) + (tokens.expires_in ?? 300),
  });
  return { id, returnTo: pending.returnTo };
}

/** Refreshes on the server shortly before the access token expires. Returns null when the session must end. */
export async function refreshIfNeeded(
  config: PortalConfig,
  store: SessionStore,
  id: string,
  session: Session,
): Promise<Session | null> {
  if (session.expiresAt - REFRESH_MARGIN_SECONDS > Math.floor(Date.now() / 1000)) return session;
  if (!session.refreshToken) return null;
  try {
    const tokens = await client.refreshTokenGrant(await oidc(config), session.refreshToken);
    const access = decodePayload(tokens.access_token);
    const updated: Session = {
      ...session,
      roles: rolesFrom(access),
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token ?? session.refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) + (tokens.expires_in ?? 300),
    };
    await store.update(id, updated);
    return updated;
  } catch {
    await store.destroy(id);
    return null;
  }
}

export async function logoutUrl(config: PortalConfig, session: Session | null): Promise<URL> {
  return client.buildEndSessionUrl(await oidc(config), {
    post_logout_redirect_uri: `${config.baseUrl}/`,
    ...(session?.idToken ? { id_token_hint: session.idToken } : {}),
  });
}
