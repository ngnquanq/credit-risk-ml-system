import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import type { Realm } from "./config";
import { completeLogin, logoutUrl, startLogin } from "./oidc";
import { portal, sessionCookieOptions } from "./server";
import { SESSION_COOKIE } from "./session";

/** Route handlers shared by both portals: /auth/login, /auth/callback, /auth/logout. */
export function authRoutes(realm: Realm) {
  return {
    async login(request: NextRequest) {
      const { config, store } = portal(realm);
      const url = await startLogin(config, store, request.nextUrl.searchParams.get("returnTo") ?? "/");
      return NextResponse.redirect(url);
    },

    async callback(request: NextRequest) {
      const { config, store } = portal(realm);
      const callbackUrl = new URL(`${config.baseUrl}${request.nextUrl.pathname}${request.nextUrl.search}`);
      try {
        const { id, returnTo } = await completeLogin(config, store, callbackUrl);
        const response = NextResponse.redirect(new URL(returnTo, config.baseUrl));
        response.cookies.set(SESSION_COOKIE, id, sessionCookieOptions);
        return response;
      } catch {
        return NextResponse.redirect(new URL("/auth/error", config.baseUrl));
      }
    },

    async logout() {
      const { config, store } = portal(realm);
      const id = cookies().get(SESSION_COOKIE)?.value;
      const session = await store.get(id);
      if (id) await store.destroy(id);
      const response = NextResponse.redirect(await logoutUrl(config, session));
      response.cookies.delete(SESSION_COOKIE);
      return response;
    },
  };
}
