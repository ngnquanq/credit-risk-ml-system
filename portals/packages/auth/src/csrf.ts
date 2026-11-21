import { timingSafeEqual } from "node:crypto";
import type { Session } from "./session";

export const CSRF_FIELD = "csrf_token";

/** Mutations must carry the session's CSRF token and come from our own origin. */
export function verifyMutation(
  session: Session,
  submittedToken: FormDataEntryValue | null,
  originHeader: string | null,
  expectedOrigin: string,
): boolean {
  if (originHeader !== expectedOrigin) return false;
  if (typeof submittedToken !== "string") return false;
  const a = Buffer.from(submittedToken);
  const b = Buffer.from(session.csrfToken);
  return a.length === b.length && timingSafeEqual(a, b);
}
