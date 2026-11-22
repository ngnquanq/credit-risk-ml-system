import { paths, type MyApplication } from "@crs/api";
import { api, requireSession } from "@crs/auth/server";
import { Card, StatusBadge, formatDateTimeVi, formatVnd, shortRef } from "@crs/ui";

export const dynamic = "force-dynamic";

export default async function MyApplications() {
  const session = await requireSession("customers", ["applicant"]);
  const applications = await api<MyApplication[]>("customers", session, paths.myApplications);
  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <h1 style={{ margin: 0 }}>Hồ sơ của tôi</h1>
      {applications.length === 0 ? (
        <Card>
          <p style={{ margin: 0 }}>Bạn chưa có hồ sơ nào.</p>
          <a href="/#estimator" className="btn btn-primary">Ước tính khoản vay</a>
        </Card>
      ) : (
        <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {applications.map((a) => (
            <li key={a.id}>
              <a href={`/applications/${encodeURIComponent(a.id)}`} className="card row"
                style={{ justifyContent: "space-between", color: "var(--black)", textDecoration: "none" }}>
                <span className="stack" style={{ gap: 2 }}>
                  <strong>{shortRef(a.id)} · <span className="amount">{formatVnd(a.amt_credit)}</span></strong>
                  <span className="muted" style={{ fontSize: 13 }}>Nộp {formatDateTimeVi(a.created_at)}</span>
                </span>
                <StatusBadge status={a.status} locale="vi" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
