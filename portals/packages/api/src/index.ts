/**
 * Shapes returned by the Loan API (contracts/openapi/loan-api.json).
 * `pnpm generate:api` writes the full generated types to schema.d.ts; these hand-kept
 * aliases cover what the portals read and are checked against it in CI.
 */

export type ApplicationStatus = "submitted" | "approved" | "rejected" | "manual_review";

export interface Reason {
  code: string;
  text: string;
}

/** GET /api/v1/applications/{id}/decision: applicant and loan officer view, no score. */
export interface DecisionView {
  customer_id: string;
  status: ApplicationStatus;
  decided_at: string | null;
  reasons: Reason[];
}

/** GET /api/v1/applications/{id}/explanation: underwriter and auditor only. */
export interface ExplanationView {
  customer_id: string;
  status: ApplicationStatus;
  decided_at: string;
  band: "APPROVE" | "UNDER_REVIEW" | "REJECT" | null;
  score: number | null;
  bands: { approve_below: number; reject_above: number } | null;
  reasons: string[] | null;
  reason_codes: string[] | null;
  contributions: Record<string, number> | null;
  explanation: { base_value: number; margin: number; additive_ok: boolean } | null;
  model: string | null;
  model_version: string | null;
  feature_set_sha256: string | null;
}

export interface ReviewItem {
  customer_id: string;
  since: string;
  score: number | null;
  reasons: string[];
  branch_id: string | null;
  can_review: boolean;
}

export interface AuditEventView {
  id: number;
  occurred_at: string;
  actor_sub: string;
  actor_realm: string;
  actor_roles: string[];
  action: string;
  resource_type: string;
  resource_id: string;
  outcome: "allowed" | "denied" | "error";
  details: Record<string, unknown>;
}

export interface PolicyChangeView {
  id: number;
  state: "proposed" | "active" | "rejected" | "expired" | "superseded";
  payload: { approve_below: number; reject_above: number; rationale: string };
  proposed_by: string;
  approved_by: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface ApplicationInput {
  sk_id_curr: string;
  birth_date: string;
  cnt_children: number;
  amt_income_total: number;
  amt_credit: number;
  amt_annuity?: number;
  amt_goods_price?: number;
  name_income_type: string;
  name_education_type: string;
  name_family_status: string;
  name_housing_type: string;
  employment_start_date?: string;
  organization_type?: string;
  document_ids?: Record<string, string>;
  bureau_consent: boolean;
}

export const paths = {
  application: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}`,
  decision: (id: string, locale: "vi" | "en" = "vi") =>
    `/api/v1/applications/${encodeURIComponent(id)}/decision?locale=${locale}`,
  explanation: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/explanation`,
  reviews: "/api/v1/reviews",
  reviewDecision: (id: string) => `/api/v1/reviews/${encodeURIComponent(id)}/decision`,
  audit: (resource: string) => `/api/v1/audit?resource=${encodeURIComponent(resource)}`,
  policyChanges: "/api/v1/policy-changes",
  policyDecision: (id: number) => `/api/v1/policy-changes/${id}/decision`,
  applications: "/api/v1/applications",
  presignedUrl: "/api/v1/presigned-url",
} as const;

/** Monthly instalment for the estimator (annuity formula); the rate is illustrative, not an offer. */
export function monthlyInstalment(amount: number, months: number, annualRatePct: number): number {
  const r = annualRatePct / 100 / 12;
  if (r === 0) return amount / months;
  return (amount * r) / (1 - Math.pow(1 + r, -months));
}
