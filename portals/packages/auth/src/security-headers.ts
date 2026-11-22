import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "./cookies"; // edge-safe: never import ./session here (node:crypto, ioredis)

/**
 * Edge middleware shared by both portals:
 * - strict CSP with a per-request nonce (Next applies it to its own scripts),
 * - other security headers,
 * - redirect to sign-in when there is no session cookie (the server re-checks the session).
 */
/** Origin browsers upload documents to (presigned POST); anything but a bare http(s) origin is ignored. */
export function storageOrigin(value: string | undefined = process.env.STORAGE_PUBLIC_ORIGIN): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const origin = url.origin;
    if (!/^https?:$/.test(url.protocol) || value.replace(/\/$/, "") !== origin) return null;
    return origin;
  } catch {
    return null;
  }
}

export function securityMiddleware(request: NextRequest, publicPaths: string[]): NextResponse {
  const nonce = btoa(crypto.randomUUID());
  const storage = storageOrigin();
  const csp = [
    "default-src 'self'",
    // Next's dev server needs eval for hot reload; production builds never get it.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${process.env.NODE_ENV === "production" ? "" : " 'unsafe-eval'"}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    // Document uploads go straight from the browser to storage, and nowhere else.
    `connect-src 'self'${storage ? ` ${storage}` : ""}`,
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
