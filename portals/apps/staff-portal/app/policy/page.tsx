import { paths, type PolicyChangeView } from "@crs/api";
import { ApiError, api, assertMutation, requireSession } from "@crs/auth/server";
import { Card, CsrfField } from "@crs/ui";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

async function propose(form: FormData) {
  "use server";
  const session = await requireSession("staff", ["risk_manager"]);
  assertMutation("staff", session, form);
  await api("staff", session, paths.policyChanges, {
    method: "POST",
    body: JSON.stringify({
      approve_below: Number(form.get("approve_below")),
      reject_above: Number(form.get("reject_above")),
      rationale: String(form.get("rationale")),
    }),
  });
  redirect("/policy");
}

async function decide(form: FormData) {
  "use server";
  const session = await requireSession("staff", ["risk_manager"]);
  assertMutation("staff", session, form);
  try {
    await api("staff", session, paths.policyDecision(Number(form.get("id"))), {
      method: "POST",
      body: JSON.stringify({ approve: form.get("approve") === "true" }),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) redirect("/forbidden"); // four eyes: not your own proposal
    throw error;
  }
  redirect("/policy");
}

export default async function PolicyPage() {
  const session = await requireSession("staff", ["risk_manager"]);
  const changes = await api<PolicyChangeView[]>("staff", session, paths.policyChanges);
  const active = changes.find((c) => c.state === "active");

  return (
    <div className="stack">
      <Card title="Active decision bands">
        {active ? (
          <p style={{ margin: 0 }}>
            Approve below {active.payload.approve_below}, reject above {active.payload.reject_above}; manual review between.
            Approved by {active.approved_by}.
          </p>
        ) : (
          <p className="muted" style={{ margin: 0 }}>Service defaults (0.25 / 0.35) until a change is approved.</p>
        )}
      </Card>
      <Card title="Propose a change">
        <form action={propose} className="stack">
          <CsrfField token={session.csrfToken} />
          <div className="grid">
            <div className="field"><label htmlFor="approve_below">Approve below</label><input id="approve_below" name="approve_below" type="number" step="0.01" min="0.01" max="0.99" required /></div>
            <div className="field"><label htmlFor="reject_above">Reject above</label><input id="reject_above" name="reject_above" type="number" step="0.01" min="0.01" max="0.99" required /></div>
          </div>
          <div className="field"><label htmlFor="rationale">Rationale (cost matrix, expected loss)</label><textarea id="rationale" name="rationale" rows={3} required minLength={10} /></div>
          <button className="btn btn-primary" type="submit">Propose</button>
        </form>
      </Card>
      <Card title="Pending approvals">
        {changes.filter((c) => c.state === "proposed").map((c) => (
          <form key={c.id} action={decide} className="row" style={{ justifyContent: "space-between" }}>
            <CsrfField token={session.csrfToken} />
            <input type="hidden" name="id" value={c.id} />
            <span>
              #{c.id}: {c.payload.approve_below} / {c.payload.reject_above} by {c.proposed_by} · {c.payload.rationale}
            </span>
            {c.proposed_by === session.sub ? (
              <span className="muted">Needs another risk manager</span>
            ) : (
              <span className="row">
                <button className="btn btn-primary" name="approve" value="true" type="submit">Approve</button>
                <button className="btn" name="approve" value="false" type="submit">Reject</button>
              </span>
            )}
          </form>
        ))}
      </Card>
    </div>
  );
}
