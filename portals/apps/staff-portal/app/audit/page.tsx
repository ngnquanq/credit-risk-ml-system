import { paths, type AuditEventView } from "@crs/api";
import { api, requireSession } from "@crs/auth/server";
import { Card } from "@crs/ui";

export const dynamic = "force-dynamic";

export default async function DecisionTrace({ searchParams }: { searchParams: { id?: string } }) {
  const session = await requireSession("staff", ["auditor"]);
  const id = (searchParams.id ?? "").trim();
  const trace = /^[A-Za-z0-9_.:-]{1,64}$/.test(id)
    ? await api<{ events: AuditEventView[] }>("staff", session, paths.audit(`application:${id}`))
    : null;

  return (
    <div className="stack">
      <form className="row" method="get">
        <div className="field">
          <label htmlFor="id">Application ID</label>
          <input id="id" name="id" defaultValue={id} required />
        </div>
        <button className="btn btn-primary" type="submit" style={{ alignSelf: "flex-end" }}>Trace</button>
      </form>
      {trace ? (
        <Card title={`Timeline · ${trace.events.length} events`}>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Outcome</th><th>Details</th></tr></thead>
              <tbody>
                {trace.events.map((e) => (
                  <tr key={e.id} style={e.outcome === "denied" ? { background: "var(--red-tint)" } : undefined}>
                    <td>{e.id}</td>
                    <td>{new Date(e.occurred_at).toLocaleString("en-GB")}</td>
                    <td>{e.actor_sub} · {e.actor_roles.join(", ")}</td>
                    <td>{e.action}</td>
                    <td>{e.outcome}</td>
                    <td><code>{JSON.stringify(e.details)}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>Your search is itself recorded. Details never contain personal data.</p>
        </Card>
      ) : null}
    </div>
  );
}
