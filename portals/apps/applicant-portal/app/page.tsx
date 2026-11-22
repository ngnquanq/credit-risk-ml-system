import { DEFAULT_DRAFT } from "@crs/auth";
import { readLoanDraft } from "@crs/auth/server";
import { Estimator } from "./Estimator";

export const dynamic = "force-dynamic";

const STEPS: [string, string][] = [
  ["Ước tính", "Chọn số tiền và kỳ hạn phù hợp với thu nhập của bạn."],
  ["Điền hồ sơ", "CCCD, công việc và thu nhập. Bạn chọn có cho phép tra cứu tín dụng hay không."],
  ["Nhận kết quả", "Theo dõi trạng thái trực tuyến; nếu cần thẩm định thêm, bạn biết lý do."],
];

export default async function Home() {
  // "Sửa" on /apply comes back here with the previous choice.
  const draft = (await readLoanDraft("customers").catch(() => null)) ?? DEFAULT_DRAFT;
  return (
    <div className="stack" style={{ gap: 40 }}>
      <div className="grid" style={{ alignItems: "center" }}>
        <div className="stack">
          <h1 className="hero-title">
            Vay tiêu dùng,
            <br />
            <span style={{ color: "var(--red)" }}>biết trước số tiền góp</span>
          </h1>
          <p className="muted" style={{ fontSize: 18, lineHeight: 1.6, margin: 0 }}>
            Ước tính miễn phí, nộp hồ sơ trực tuyến với CCCD. Nếu hồ sơ cần xem thêm, bạn được biết lý do và việc cần
            làm tiếp theo.
          </p>
          <ul className="row" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            <li className="badge">Chỉ cần CCCD</li>
            <li className="badge">Kết quả kèm lý do</li>
            <li className="badge">Chỉ tra cứu tín dụng khi bạn đồng ý</li>
          </ul>
        </div>
        <Estimator initialAmount={draft.amount} initialTerm={draft.term} />
      </div>
      <section className="stack" aria-labelledby="steps-title">
        <h2 id="steps-title" style={{ margin: 0 }}>3 bước</h2>
        <ol className="steps">
          {STEPS.map(([title, text], i) => (
            <li key={title} className="card">
              <span className="step-num" aria-hidden="true">{i + 1}</span>
              <div>
                <strong>{title}</strong>
                <p className="muted" style={{ margin: "4px 0 0" }}>{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
