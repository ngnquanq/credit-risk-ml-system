import { paths, type ReviewItem } from "@crs/api";
import { api, requireSession } from "@crs/auth/server";
import { Card, formatVnd, shortRef } from "@crs/ui";

export const dynamic = "force-dynamic";

export default async function ReviewQueue() {
  const session = await requireSession("staff", ["underwriter"]);
  const queue = await api<ReviewItem[]>("staff", session, paths.reviews);
  return (
    <Card title={`Review queue · ${queue.length} waiting · oldest first`}>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Application</th><th>Amount</th><th>Waiting since</th><th>Why</th><th>Branch</th><th /></tr>
          </thead>
          <tbody>
            {queue.map((item) => (
              <tr key={item.application_id}>
                <td>{shortRef(item.application_id)}</td>
                <td className="amount">{formatVnd(item.amt_credit)}</td>
                <td>{new Date(item.since).toLocaleString("en-GB")}</td>
                <td>{item.reasons.join(", ")}</td>
                <td>{item.branch_id ?? "online"}</td>
                <td>
                  {item.can_review ? (
                    <a className="btn" href={`/reviews/${encodeURIComponent(item.application_id)}`}>Open</a>
                  ) : (
                    <span className="muted">You submitted this one</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
