import { paths, type DecisionView } from "@crs/api";
import { ApiError, api, assertMutation, requireSession } from "@crs/auth/server";
import { Card, CsrfField, ReasonList, StatusBadge } from "@crs/ui";
import { notFound, redirect } from "next/navigation";

export const dynamic = "force-dynamic";

interface CustomerProfile {
  contracts: { contract: string; product: string; amount: number; status: string }[];
  exposure: number | null;
  on_time_ratio: number | null;
  max_days_past_due: number | null;
  bureau: { active_credits: number | null; outstanding: number | null; overdue: number | null } | null;
}

async function addNote(form: FormData) {
  "use server";
  const session = await requireSession("staff", ["loan_officer"]);
  assertMutation("staff", session, form);
  const id = String(form.get("id"));
  await api("staff", session, `${paths.application(id)}/notes`, {
    method: "POST",
    body: JSON.stringify({ kind: String(form.get("kind")), text: String(form.get("text")) }),
  });
  redirect(`/cases/${encodeURIComponent(id)}`);
}

const vnd = new Intl.NumberFormat("en-US");

/** Loan officer case view (ADR-0013): internal factors for the customer being served, plain reasons, no score. */
export default async function CaseView({ params }: { params: { id: string } }) {
  const session = await requireSession("staff", ["loan_officer"]);
  let decision: DecisionView;
  try {
    decision = await api<DecisionView>("staff", session, paths.decision(params.id, "en"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    if (error instanceof ApiError && error.status === 403) redirect("/forbidden");
    throw error;
  }
  const profile = await api<CustomerProfile>("staff", session, `${paths.application(params.id)}/customer-profile`).catch(
    () => null,
  );

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0 }}>Application {decision.customer_id}</h1>
        <StatusBadge status={decision.status} />
      </div>
      <div className="grid">
        <Card title="Relationship with us (internal)">
          {profile ? (
            <>
              <div className="row">
                <span className="badge">Exposure {profile.exposure == null ? "–" : `${vnd.format(profile.exposure)} ₫`}</span>
                <span className="badge">On time {profile.on_time_ratio == null ? "–" : `${Math.round(profile.on_time_ratio * 100)}%`}</span>
                <span className="badge">Max days past due {profile.max_days_past_due ?? "–"}</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Contract</th><th>Product</th><th>Amount</th><th>Status</th></tr></thead>
                  <tbody>
                    {profile.contracts.map((c) => (
                      <tr key={c.contract}><td>{c.contract}</td><td>{c.product}</td><td>{vnd.format(c.amount)} ₫</td><td>{c.status}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {profile.bureau ? (
                <p className="muted" style={{ margin: 0 }}>
                  Bureau: {profile.bureau.active_credits ?? 0} active credits, outstanding {vnd.format(profile.bureau.outstanding ?? 0)} ₫
                </p>
              ) : null}
            </>
          ) : (
            <p className="muted" style={{ margin: 0 }}>Available only for applications you entered, after the customer's consent.</p>
          )}
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>Every view is logged with its purpose.</p>
        </Card>
        <Card title="Decision">
          <p style={{ margin: 0 }}>An underwriter decides borderline cases. You cannot approve, reject or change this outcome.</p>
          <h3 style={{ margin: 0, fontSize: 15 }}>Reasons the customer sees</h3>
          <ReasonList reasons={decision.reasons} />
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>Model score and factor weights are visible to underwriters only.</p>
        </Card>
      </div>
      <Card title="Note for the underwriter">
        <form action={addNote} className="stack">
          <CsrfField token={session.csrfToken} />
          <input type="hidden" name="id" value={decision.customer_id} />
          <div className="field">
            <label htmlFor="kind">Type</label>
            <select id="kind" name="kind">
              <option value="note">Verification note</option>
              <option value="concern">Concern (fraud, document mismatch)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="text">Facts you verified in person</label>
            <textarea id="text" name="text" rows={4} required minLength={10} maxLength={1000} />
          </div>
          <button className="btn btn-primary" type="submit">Attach to case</button>
        </form>
      </Card>
    </div>
  );
}
