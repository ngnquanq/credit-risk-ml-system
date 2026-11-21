import type { NextRequest } from "next/server";
import { securityMiddleware } from "@crs/auth/middleware";

// Nothing in the staff portal is public.
export function middleware(request: NextRequest) {
  return securityMiddleware(request, ["/forbidden"]);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
