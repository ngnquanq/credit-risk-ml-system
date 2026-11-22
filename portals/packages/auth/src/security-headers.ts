import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "./cookies"; // edge-safe: never import ./session here (node:crypto, ioredis)

/**
 * Edge middleware shared by both portals:
 * - strict CSP with a per-request nonce (Next applies it to its own scripts),
 * - other security headers,
 * - redirect to sign-in when there is no session cookie (the server re-checks the session).
 */
export function securityMiddleware(request: NextRequest, publicPaths: string[]): NextResponse {
  const nonce = btoa(crypto.randomUUID());
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'none'",
    "object-src 'none'",
  ].join("; ");

  const path = request.nextUrl.pathname;
  const isPublic = publicPaths.some((p) => path === p || path.startsWith(`${p}/`)) || path.startsWith("/auth/");
  if (!isPublic && !request.cookies.get(SESSION_COOKIE)) {
    const login = new URL("/auth/login", request.url);
    login.searchParams.set("returnTo", path + request.nextUrl.search);
    return NextResponse.redirect(login);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("x-pathname", path + request.nextUrl.search);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  response.headers.set("Cache-Control", "no-store");
  return response;
}
