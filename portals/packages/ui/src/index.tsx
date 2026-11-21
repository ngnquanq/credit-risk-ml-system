import type { ReactNode } from "react";

export type Status = "submitted" | "approved" | "rejected" | "manual_review";

const STATUS_LABEL: Record<"vi" | "en", Record<Status, string>> = {
  vi: { submitted: "Đã nhận hồ sơ", approved: "Đã duyệt", rejected: "Chưa được duyệt", manual_review: "Cần thẩm định thêm" },
  en: { submitted: "Submitted", approved: "Approved", rejected: "Rejected", manual_review: "Manual review" },
};

export function StatusBadge({ status, locale = "en" }: { status: Status; locale?: "vi" | "en" }) {
  const cls = status === "rejected" ? "badge badge-reject" : "badge";
  return <span className={cls}>{STATUS_LABEL[locale][status]}</span>;
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card stack">
      {title || actions ? (
        <div className="row" style={{ justifyContent: "space-between" }}>
          {title ? <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Plain-language reasons, ordered by contribution. Never shows scores or weights. */
export function ReasonList({ reasons }: { reasons: { code: string; text: string }[] }) {
  if (reasons.length === 0) return null;
  return (
    <ol className="stack" style={{ margin: 0, paddingLeft: 20, gap: 8 }}>
      {reasons.map((r) => (
        <li key={r.code}>{r.text}</li>
      ))}
    </ol>
  );
}

/** Diverging bars for SHAP contributions (underwriters only): red raises risk, dark grey lowers it. */
export function ContributionBars({ contributions, limit = 8 }: { contributions: Record<string, number>; limit?: number }) {
  const entries = Object.entries(contributions).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, limit);
  const max = Math.max(...entries.map(([, v]) => Math.abs(v)), 1e-9);
  return (
    <div className="stack" style={{ gap: 6 }} role="img" aria-label="Model contributions per input">
      <div className="row muted" style={{ justifyContent: "space-between", fontSize: 12 }}>
        <span>◀ lowers risk</span>
        <span>raises risk ▶</span>
      </div>
      {entries.map(([name, value]) => (
        <div key={name} style={{ display: "grid", gridTemplateColumns: "190px minmax(0,1fr) 56px", gap: 8, alignItems: "center", fontSize: 13 }}>
          <span>{name}</span>
          <div style={{ display: "flex", height: 14 }}>
            <div style={{ flex: 1, display: "flex", justifyContent: "flex-end", borderRight: "1px solid var(--grey-400)" }}>
              {value < 0 ? <div style={{ width: `${(Math.abs(value) / max) * 100}%`, background: "var(--grey-600)" }} /> : null}
            </div>
            <div style={{ flex: 1 }}>
              {value > 0 ? <div style={{ width: `${(value / max) * 100}%`, height: 14, background: "var(--red)" }} /> : null}
            </div>
          </div>
          <span style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
            {value > 0 ? "+" : "−"}
            {Math.abs(value).toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Hidden CSRF field for server-action forms (E12). */
export function CsrfField({ token }: { token: string }) {
  return <input type="hidden" name="csrf_token" value={token} />;
}
