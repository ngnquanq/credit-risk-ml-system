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
  application_id: string;
  status: ApplicationStatus;
  amt_credit: number;
  submitted_at: string;
  decided_at: string | null;
  reasons: Reason[];
  /** Statuses and times only (ADR-0013). */
  history: { status: ApplicationStatus; at: string }[];
}

/** Name in full, citizen ID and phone masked (ADR-0014). */
export interface MaskedApplicant {
  full_name: string;
  citizen_id_masked: string;
  phone_masked: string;
}

/** GET /api/v1/applications/{id} */
export interface ApplicationView {
  id: string;
  applicant: MaskedApplicant | null;
  channel: "staff" | "self" | null;
  branch_id: string | null;
  documents: string[];
  birth_date: string;
  cnt_children: number;
  amt_income_total: number;
  amt_credit: number;
  amt_annuity: number | null;
  name_income_type: string;
  name_education_type: string;
  name_family_status: string;
  name_housing_type: string;
  employment_start_date: string | null;
  organization_type: string | null;
  created_at: string;
}

/** POST /api/v1/applications/{id}/identity:reveal (officer handling the case, underwriter in review). */
export interface RevealedIdentity {
  full_name: string;
  citizen_id: string;
  phone: string;
}

/** GET /api/v1/me/applications */
export interface MyApplication {
  id: string;
  amt_credit: number;
  created_at: string;
  status: ApplicationStatus;
}

/** POST /api/v1/customers:lookup */
export interface CustomerLookup {
  citizen_id_masked: string;
  found: boolean;
  applications: number;
  statuses: ApplicationStatus[];
  same_branch: boolean;
}

/** GET /api/v1/applications/{id}/explanation: underwriter and auditor only. */
export interface ExplanationView {
  application_id: string;
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
  application_id: string;
  since: string;
  amt_credit: number;
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

/** POST /api/v1/applications. The API resolves the internal customer key from the citizen ID. */
export interface ApplicationInput {
  applicant: { full_name: string; citizen_id: string; phone: string };
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

/** Ids in URLs are opaque public ids only; personal data goes in request bodies (ADR-0014). */
export const paths = {
  application: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}`,
  decision: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/decision`,
  revealIdentity: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/identity:reveal`,
  documents: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/documents`,
  myApplications: "/api/v1/me/applications",
  explanation: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/explanation`,
  reviews: "/api/v1/reviews",
  reviewDecision: (id: string) => `/api/v1/reviews/${encodeURIComponent(id)}/decision`,
  audit: (resource: string) => `/api/v1/audit?resource=${encodeURIComponent(resource)}`,
  policyChanges: "/api/v1/policy-changes",
  policyDecision: (id: number) => `/api/v1/policy-changes/${id}/decision`,
  applications: "/api/v1/applications",
  presignedUrl: "/api/v1/presigned-url",
  notes: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/notes`,
  customerProfile: (id: string) => `/api/v1/applications/${encodeURIComponent(id)}/customer-profile`,
  customerLookup: "/api/v1/customers:lookup",
} as const;

/** Document slots the portals use (API DOCUMENT_FOLDERS). */
export const DOCUMENT_SLOTS = { idFront: 2, idBack: 15, incomeProof: 3 } as const;

/** Illustrative annual rate for the estimator; the real rate depends on the assessment. */
export const ILLUSTRATIVE_RATE_PCT = 20;

/** Monthly instalment for the estimator (annuity formula); the rate is illustrative, not an offer. */
export function monthlyInstalment(amount: number, months: number, annualRatePct: number): number {
  const r = annualRatePct / 100 / 12;
  if (r === 0) return amount / months;
  return (amount * r) / (1 - Math.pow(1 + r, -months));
}
