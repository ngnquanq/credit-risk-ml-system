import { paths, type ExplanationView } from "@crs/api";
import { ApiError, api, assertMutation, requireSession } from "@crs/auth/server";
import { Card, ContributionBars, CsrfField } from "@crs/ui";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

interface ApplicationView {
  sk_id_curr: string;
  amt_income_total: number;
  amt_credit: number;
  amt_annuity: number | null;
  employment_start_date: string | null;
  name_income_type: string;
}

async function decide(form: FormData) {
  "use server";
  const session = await requireSession("staff", ["underwriter"]);
  assertMutation("staff", session, form);
  const id = String(form.get("id"));
  try {
    await api("staff", session, paths.reviewDecision(id), {
      method: "POST",
      body: JSON.stringify({
        outcome: String(form.get("outcome")),
        reason_code: String(form.get("reason_code")),
        reason: String(form.get("reason")),
      }),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) redirect("/forbidden"); // e.g. separation of duties
    throw error;
  }
  redirect("/reviews");
}

const vnd = new Intl.NumberFormat("en-US");

/** Three steps (ADR-0013): evidence first, then the model's explanation, then the decision. */
export default async function ReviewCase({ params }: { params: { id: string } }) {
  const session = await requireSession("staff", ["underwriter"]);
  const [application, explanation] = await Promise.all([
    api<ApplicationView>("staff", session, paths.application(params.id)),
    api<ExplanationView>("staff", session, paths.explanation(params.id)).catch(() => null),
  ]);

  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>Application {application.sk_id_curr}</h1>
      <div className="grid">
        <Card title="1 · Evidence">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            <li>Annual income {vnd.format(application.amt_income_total)} ₫ ({application.name_income_type})</li>
            <li>Credit requested {vnd.format(application.amt_credit)} ₫</li>
            <li>Current job since {application.employment_start_date ?? "not employed"}</li>
          </ul>
        </Card>
        <Card title="2 · Model explanation">
          {explanation ? (
            <>
              <div className="row">
                <span className="badge">P(default) {explanation.score?.toFixed(2) ?? "–"}</span>
                <span className="badge">
                  Band {explanation.band ?? "–"}
                  {explanation.bands ? ` (${explanation.bands.approve_below}–${explanation.bands.reject_above})` : ""}
                </span>
              </div>
              {explanation.contributions ? <ContributionBars contributions={explanation.contributions} /> : null}
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                Model {explanation.model_version ?? "?"} · feature set {explanation.feature_set_sha256?.slice(0, 8) ?? "?"}. Contributions
                explain the model, not the applicant&apos;s situation.
              </p>
            </>
          ) : (
            <p className="muted" style={{ margin: 0 }}>No automated score: features were incomplete or scoring was unavailable.</p>
          )}
        </Card>
      </div>
      <Card title="3 · Your decision">
        <form action={decide} className="stack">
          <CsrfField token={session.csrfToken} />
          <input type="hidden" name="id" value={application.sk_id_curr} />
          <fieldset className="row" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="visually-hidden">Outcome</legend>
            <label className="row"><input type="radio" name="outcome" value="approved" required /> Approve</label>
            <label className="row"><input type="radio" name="outcome" value="rejected" /> Reject</label>
          </fieldset>
          <div className="grid">
            <div className="field">
              <label htmlFor="reason_code">Reason code</label>
              <select id="reason_code" name="reason_code">
                <option value="INCOME_VERIFIED">Income verified by documents</option>
                <option value="AFFORDABILITY_NOT_SHOWN">Affordability not demonstrated</option>
                <option value="BRANCH_CONCERN">Concern raised by the branch</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="reason">Reason (required)</label>
              <textarea id="reason" name="reason" rows={2} required minLength={10} maxLength={1000} />
            </div>
          </div>
          <button className="btn btn-primary" type="submit">Record decision</button>
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>Recorded with your identity and the reason in the audit trail.</p>
        </form>
      </Card>
    </div>
  );
}
