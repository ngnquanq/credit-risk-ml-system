"use server";

import { DOCUMENT_SLOTS, ILLUSTRATIVE_RATE_PCT, monthlyInstalment, paths, type ApplicationInput } from "@crs/api";
import { DEFAULT_DRAFT } from "@crs/auth";
import {
  ApiError,
  api,
  assertMutation,
  assertSameOrigin,
  clearLoanDraft,
  readLoanDraft,
  requireSession,
  saveLoanDraft,
} from "@crs/auth/server";
import type { UploadTicket } from "@crs/ui";
import { redirect } from "next/navigation";

const CONTENT_TYPES = new Set(["image/jpeg", "image/png", "application/pdf"]);
const SLOTS = new Set<number>(Object.values(DOCUMENT_SLOTS));

/** Upload policy for one document; the browser then posts the file straight to storage. */
export async function requestUpload(slot: number, contentType: string): Promise<UploadTicket> {
  assertSameOrigin("customers");
  const session = await requireSession("customers", ["applicant"]);
  if (!SLOTS.has(slot) || !CONTENT_TYPES.has(contentType)) throw new Error("Unsupported document");
  return api<UploadTicket>("customers", session, paths.presignedUrl, {
    method: "POST",
    body: JSON.stringify({ document_type: slot, content_type: contentType }),
  });
}

/** Attach an uploaded document to an open application (status page, e.g. payslips during review). */
export async function attachDocument(applicationId: string, slot: number, documentId: string): Promise<void> {
  assertSameOrigin("customers");
  const session = await requireSession("customers", ["applicant"]);
  await api("customers", session, paths.documents(applicationId), {
    method: "POST",
    body: JSON.stringify({ slot, document_id: documentId }),
  });
}

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

export async function submitApplication(form: FormData): Promise<void> {
  const session = await requireSession("customers", ["applicant"]);
  assertMutation("customers", session, form);
  // The loan comes from the draft the estimator saved, not from editable form fields.
  const draft = (await readLoanDraft("customers")) ?? DEFAULT_DRAFT;
  const monthlyIncome = Number(text(form, "monthly_income"));
  const documentIds: Record<string, string> = {};
  for (const slot of SLOTS) {
    const id = text(form, `document_id_${slot}`);
    if (id) documentIds[`document_id_${slot}`] = id;
  }
  const body: ApplicationInput = {
    applicant: { full_name: text(form, "full_name"), citizen_id: text(form, "citizen_id"), phone: text(form, "phone") },
    birth_date: text(form, "birth_date"),
    cnt_children: Number(text(form, "cnt_children") || 0),
    amt_income_total: monthlyIncome * 12,
    amt_credit: draft.amount,
    amt_annuity: Math.round(monthlyInstalment(draft.amount, draft.term, ILLUSTRATIVE_RATE_PCT)),
    amt_goods_price: draft.amount,
    name_income_type: text(form, "name_income_type"),
    name_education_type: text(form, "name_education_type"),
    name_family_status: text(form, "name_family_status"),
    name_housing_type: text(form, "name_housing_type"),
    employment_start_date: text(form, "employment_start_date") || undefined,
    document_ids: documentIds,
    bureau_consent: form.get("bureau_consent") === "on",
  };

  let created: { id: string };
  try {
    // Ownership (channel=self, applicant_sub) is set by the API from the token, never from this body.
    created = await api<{ id: string }>("customers", session, paths.applications, {
      method: "POST",
      body: JSON.stringify(body),
    });
  } catch (error) {
    const flash = !(error instanceof ApiError) ? "failed"
      : error.status === 409 ? "exists"
      : JSON.stringify(error.body ?? "").includes("document") ? "documents"
      : error.status === 422 ? "invalid" : "failed";
    await saveLoanDraft("customers", { ...draft, flash });
    redirect("/apply");
  }
  await clearLoanDraft("customers");
  redirect(`/applications/${encodeURIComponent(created.id)}`);
}
