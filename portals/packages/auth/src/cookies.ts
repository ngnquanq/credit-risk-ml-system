/**
 * Edge-safe constants. The middleware (Edge runtime) imports this file, so it must not import
 * anything that needs Node (node:crypto, ioredis).
 */
export const SESSION_COOKIE = "__Host-session";
