import type { NextRequest } from "next/server";
import { securityMiddleware } from "@crs/auth/middleware";

// The estimator and legal pages are public; everything else needs a session.
export function middleware(request: NextRequest) {
  return securityMiddleware(request, ["/", "/privacy", "/forbidden"]);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
