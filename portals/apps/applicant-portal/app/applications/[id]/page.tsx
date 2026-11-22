import { paths, type ApplicationStatus, type DecisionView } from "@crs/api";
import { ApiError, api, requireSession } from "@crs/auth/server";
import { Card, ReasonList, StatusBadge, Timeline, formatDateTimeVi, formatVnd, shortRef, type TimelineItem } from "@crs/ui";
import { notFound } from "next/navigation";
import { PayslipUpload } from "./PayslipUpload";

export const dynamic = "force-dynamic";

const HEADLINE: Record<ApplicationStatus, { title: string; text: string; icon: string }> = {
  submitted: {
    title: "Hồ sơ đang được đánh giá",
    text: "Hệ thống đang đánh giá hồ sơ. Trang sẽ có kết quả sau ít phút; bạn có thể tải lại trang.",
    icon: "…",
  },
  manual_review: {
    title: "Hồ sơ cần thẩm định thêm",
    text: "Một chuyên viên sẽ xem hồ sơ của bạn. Bạn không cần nộp lại hồ sơ; tải lên sao kê lương sẽ giúp duyệt nhanh hơn.",
    icon: "!",
  },
  approved: {
    title: "Hồ sơ đã được duyệt",
    text: "Chi nhánh sẽ liên hệ để ký hợp đồng. Vui lòng mang theo CCCD bản gốc.",
    icon: "✓",
  },
  rejected: {
    title: "Hồ sơ chưa được duyệt",
    text: "Dưới đây là các yếu tố ảnh hưởng nhiều nhất. Bạn có thể yêu cầu giải thích chi tiết hoặc khiếu nại.",
    icon: "×",
  },
};

const STEP_LABEL: Record<ApplicationStatus, string> = {
  submitted: "Đã nhận hồ sơ",
  manual_review: "Chuyên viên thẩm định",
  approved: "Đã duyệt",
  rejected: "Chưa được duyệt",
};

function timeline(decision: DecisionView): TimelineItem[] {
  const items: TimelineItem[] = decision.history.map((h, i) => ({
    label: i > 0 && h.status === "manual_review" ? "Đã đánh giá tự động · cần thẩm định" : STEP_LABEL[h.status],
    at: h.at,
    state: "done",
  }));
  if (decision.status === "submitted") items.push({ label: "Đánh giá tự động", state: "current" });
  if (decision.status === "manual_review") items.push({ label: "Chuyên viên thẩm định", state: "current" });
  if (decision.status === "submitted" || decision.status === "manual_review") items.push({ label: "Kết quả", state: "todo" });
  return items;
}

export default async function ApplicationStatusPage({ params }: { params: { id: string } }) {
  const session = await requireSession("customers", ["applicant"]);
  let decision: DecisionView;
  try {
    decision = await api<DecisionView>("customers", session, paths.decision(params.id));
  } catch (error) {
    // Another applicant's file looks the same as a missing one (E12 AC4); the API audits the denial.
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) notFound();
    throw error;
  }
  const head = HEADLINE[decision.status];

  return (
    <div className="stack">
      <div className="stack" style={{ gap: 4 }}>
        <div className="row">
          <h1 style={{ margin: 0 }}>Hồ sơ {shortRef(decision.application_id)}</h1>
          <StatusBadge status={decision.status} locale="vi" />
        </div>
        <p className="muted" style={{ margin: 0 }}>
          <span className="amount">{formatVnd(decision.amt_credit)}</span> · nộp {formatDateTimeVi(decision.submitted_at)}
        </p>
      </div>

      <div className="layout-2col">
        <div className="stack">
          <Card>
            <div className="status-head">
              <span className={`status-icon ${decision.status}`} aria-hidden="true">{head.icon}</span>
              <div className="stack" style={{ gap: 4 }}>
                <h2 style={{ margin: 0, fontSize: 20 }}>{head.title}</h2>
                <p style={{ margin: 0 }}>{head.text}</p>
              </div>
            </div>
          </Card>
          {decision.reasons.length > 0 ? (
            <Card title="Những yếu tố ảnh hưởng nhiều nhất">
              <p className="muted" style={{ margin: 0, fontSize: 14 }}>
                Các yếu tố trong hồ sơ ảnh hưởng nhiều nhất đến kết quả đánh giá, xếp từ nhiều đến ít.
              </p>
              <ReasonList reasons={decision.reasons} />
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Các yếu tố mô tả cách mô hình đánh giá hồ sơ, không phải nhận xét về cá nhân bạn. Hồ sơ không bao giờ bị
                từ chối chỉ vì hệ thống gặp sự cố.
              </p>
            </Card>
          ) : null}
          <Card title="Bạn có thể làm gì">
            {decision.status === "manual_review" ? <PayslipUpload applicationId={decision.application_id} /> : null}
            <a href="/support" className="btn" style={{ alignSelf: "flex-start" }}>Yêu cầu giải thích chi tiết hoặc khiếu nại</a>
          </Card>
        </div>
        <aside>
          <Card title="Tiến trình">
            <Timeline items={timeline(decision)} />
          </Card>
        </aside>
      </div>
    </div>
  );
}
