import { paths, type DecisionView } from "@crs/api";
import { ApiError, api, assertMutation, requireSession } from "@crs/auth/server";
import { Card, CsrfField, ReasonList, StatusBadge } from "@crs/ui";
import { notFound, redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/** GET /api/v1/applications/{id}/customer-profile: aggregates only (ADR-0013). */
interface CustomerProfile {
  previous_applications: { count: number | null; refusal_rate: number | null };
  pos_loans: { count: number | null; problem_loans: number | null; max_days_past_due: number | null; months_observed: number | null };
  credit_card: { utilization: number | null };
  bureau: { active_credits: number | null; outstanding: number | null; overdue_count: number | null };
}

const show = (v: number | null | undefined, suffix = "") => (v == null ? "–" : `${v}${suffix}`);

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
              <div className="table-wrap">
                <table>
                  <tbody>
                    <tr><th scope="row">Previous applications</th><td>{show(profile.previous_applications.count)}</td>
                      <td>refused {profile.previous_applications.refusal_rate == null ? "–" : `${Math.round(profile.previous_applications.refusal_rate * 100)}%`}</td></tr>
                    <tr><th scope="row">Point-of-sale loans</th><td>{show(profile.pos_loans.count)}</td>
                      <td>problem loans {show(profile.pos_loans.problem_loans)} · max days past due {show(profile.pos_loans.max_days_past_due)}</td></tr>
                    <tr><th scope="row">History observed</th><td colSpan={2}>{show(profile.pos_loans.months_observed, " months")}</td></tr>
                    <tr><th scope="row">Credit bureau</th><td>{show(profile.bureau.active_credits)} active</td>
                      <td>outstanding {profile.bureau.outstanding == null ? "–" : `${vnd.format(profile.bureau.outstanding)} ₫`} · overdue {show(profile.bureau.overdue_count)}</td></tr>
                  </tbody>
                </table>
              </div>
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
