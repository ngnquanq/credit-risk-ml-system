"use server";

import { saveLoanDraft } from "@crs/auth/server";
import { redirect } from "next/navigation";

/**
 * Estimator -> /apply. The amount and term go into a server-side draft (httpOnly cookie), so the
 * URL stays /apply: no amounts in browser history, logs or Referer headers (ADR-0014).
 * Next checks that server actions come from this site's own origin.
 */
export async function startApplication(form: FormData): Promise<void> {
  await saveLoanDraft("customers", { amount: Number(form.get("amount")), term: Number(form.get("term")) });
  redirect("/apply");
}
