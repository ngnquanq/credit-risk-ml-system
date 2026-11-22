export type Realm = "staff" | "customers";

export interface PortalConfig {
  realm: Realm;
  issuer: string;
  clientId: string;
  clientSecret: string;
  /** Public origin of this portal, e.g. https://staff.credit.local */
  baseUrl: string;
  redisUrl: string;
  /** In-cluster Loan API, e.g. http://api-service.api-gateway.svc */
  apiBaseUrl: string;
  /** Idle and absolute session lifetimes (seconds). */
  idleTimeout: number;
  absoluteTimeout: number;
  /** Local development only: accept an http:// issuer (Keycloak on localhost). */
  allowInsecureHttp: boolean;
}

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set`);
  return value;
}

export function loadConfig(realm: Realm): PortalConfig {
  return {
    realm,
    issuer: required("OIDC_ISSUER"),
    clientId: required("OIDC_CLIENT_ID"),
    clientSecret: required("OIDC_CLIENT_SECRET"),
    baseUrl: required("PORTAL_BASE_URL").replace(/\/$/, ""),
    redisUrl: required("SESSION_REDIS_URL"),
    apiBaseUrl: required("API_BASE_URL").replace(/\/$/, ""),
    idleTimeout: Number(process.env.SESSION_IDLE_SECONDS ?? 1800),
    absoluteTimeout: Number(process.env.SESSION_ABSOLUTE_SECONDS ?? 28800),
    allowInsecureHttp: process.env.OIDC_ALLOW_INSECURE_HTTP === "true" && process.env.NODE_ENV !== "production",
  };
}
