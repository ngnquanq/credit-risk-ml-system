"use server";

import { DOCUMENT_SLOTS, paths, type RevealedIdentity } from "@crs/api";
import { ApiError, api, assertSameOrigin, requireSession } from "@crs/auth/server";
import type { UploadTicket } from "@crs/ui";

const CONTENT_TYPES = new Set(["image/jpeg", "image/png", "application/pdf"]);
const SLOTS = new Set<number>(Object.values(DOCUMENT_SLOTS));

/** Upload policy for a document scanned at the branch; the browser posts the file to storage. */
export async function requestUpload(slot: number, contentType: string): Promise<UploadTicket> {
  assertSameOrigin("staff");
  const session = await requireSession("staff", ["loan_officer"]);
  if (!SLOTS.has(slot) || !CONTENT_TYPES.has(contentType)) throw new Error("Unsupported document");
  return api<UploadTicket>("staff", session, paths.presignedUrl, {
    method: "POST",
    body: JSON.stringify({ document_type: slot, content_type: contentType }),
  });
}

export type RevealResult = { ok: true; identity: RevealedIdentity } | { ok: false; message: string };

/**
 * Unmasked citizen ID and phone for the case being worked (ADR-0014). The API decides who may,
 * audits the reason, and never logs the values; the portal only passes them to this one view.
 */
export async function revealIdentity(applicationId: string, reason: string): Promise<RevealResult> {
  assertSameOrigin("staff");
  const session = await requireSession("staff", ["loan_officer", "underwriter"]);
  if (reason.trim().length < 10) return { ok: false, message: "Give a reason of at least 10 characters." };
  try {
    const identity = await api<RevealedIdentity>("staff", session, paths.revealIdentity(applicationId), {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    return { ok: true, identity };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return { ok: false, message: "Only the officer handling this case, or an underwriter during review, may see these." };
    }
    return { ok: false, message: "Could not load the details. Try again." };
  }
}
