import { Estimator } from "./Estimator";

export default function Home() {
  return (
    <div className="stack" style={{ gap: 40 }}>
      <div className="grid" style={{ alignItems: "center" }}>
        <div className="stack">
          <h1 style={{ fontSize: 44, lineHeight: 1.15, margin: 0 }}>
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
        <Estimator />
      </div>
    </div>
  );
}
