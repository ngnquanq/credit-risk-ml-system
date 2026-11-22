/**
 * Edge-safe constants. The middleware (Edge runtime) imports this file, so it must not import
 * anything that needs Node (node:crypto, ioredis).
 */
export const SESSION_COOKIE = "__Host-session";

/** Estimator draft (amount, term) between the public home page and /apply. */
export const DRAFT_COOKIE = "__Host-draft";
