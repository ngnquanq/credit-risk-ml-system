import { randomToken, type KeyValue } from "./session";

/**
 * The estimator's choice travels from the public home page to /apply (across sign-in) as a
 * server-side draft behind an httpOnly cookie, not in the URL: amounts stay out of browser
 * history, proxy logs and Referer headers (ADR-0014).
 */
export interface LoanDraft {
  amount: number;
  term: number;
  /** One-time message for the next render of /apply (e.g. "this customer already applied"). */
  flash?: "exists" | "invalid" | "documents" | "failed";
}

export const DRAFT_LIMITS = { minAmount: 3_000_000, maxAmount: 100_000_000, step: 1_000_000, minTerm: 6, maxTerm: 36 };
export const DEFAULT_DRAFT: LoanDraft = { amount: 40_000_000, term: 24 };
const FLASHES = new Set(["exists", "invalid", "documents", "failed"]);

/** Anything outside the published ranges falls back to the defaults (the API re-validates anyway). */
export function sanitizeDraft(input: unknown): LoanDraft {
  const raw = (input ?? {}) as Record<string, unknown>;
  const amount = Number(raw.amount);
  const term = Number(raw.term);
  const okAmount = Number.isInteger(amount) && amount >= DRAFT_LIMITS.minAmount && amount <= DRAFT_LIMITS.maxAmount
    && amount % DRAFT_LIMITS.step === 0;
  const okTerm = Number.isInteger(term) && term >= DRAFT_LIMITS.minTerm && term <= DRAFT_LIMITS.maxTerm;
  const draft: LoanDraft = { amount: okAmount ? amount : DEFAULT_DRAFT.amount, term: okTerm ? term : DEFAULT_DRAFT.term };
  if (typeof raw.flash === "string" && FLASHES.has(raw.flash)) draft.flash = raw.flash as LoanDraft["flash"];
  return draft;
}

export class DraftStore {
  constructor(private readonly kv: KeyValue, private readonly ttlSeconds = 1800) {}

  /** Saves under the existing id when there is one, so the cookie stays the same. */
  async save(draft: LoanDraft, id?: string): Promise<string> {
    const key = id && /^[A-Za-z0-9_-]{20,}$/.test(id) ? id : randomToken();
    await this.kv.set(`draft:${key}`, JSON.stringify(sanitizeDraft(draft)), "EX", this.ttlSeconds);
    return key;
  }

  async get(id: string | undefined): Promise<LoanDraft | null> {
    if (!id) return null;
    const raw = await this.kv.get(`draft:${id}`);
    return raw ? sanitizeDraft(JSON.parse(raw)) : null;
  }

  async clear(id: string | undefined): Promise<void> {
    if (id) await this.kv.del(`draft:${id}`);
  }
}
