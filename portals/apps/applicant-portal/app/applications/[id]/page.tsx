import { paths, type DecisionView } from "@crs/api";
import { ApiError, api, requireSession } from "@crs/auth/server";
import { Card, ReasonList, StatusBadge } from "@crs/ui";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

const HEADLINE: Record<DecisionView["status"], string> = {
  submitted: "Hồ sơ đang được đánh giá",
  approved: "Hồ sơ đã được duyệt",
  rejected: "Hồ sơ chưa được duyệt",
  manual_review: "Hồ sơ cần thẩm định thêm",
};

export default async function ApplicationStatus({ params }: { params: { id: string } }) {
  const session = await requireSession("customers", ["applicant"]);
  let decision: DecisionView;
  try {
    decision = await api<DecisionView>("customers", session, paths.decision(params.id, "vi"));
  } catch (error) {
    // Another applicant's file looks the same as a missing one (E12 AC4); the API audits the denial.
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) notFound();
    throw error;
  }

  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <div className="row">
        <h1 style={{ margin: 0 }}>Hồ sơ #{decision.customer_id}</h1>
        <StatusBadge status={decision.status} locale="vi" />
      </div>
      <Card title={HEADLINE[decision.status]}>
        {decision.status === "submitted" ? (
          <p className="muted" style={{ margin: 0 }}>Trang sẽ cập nhật khi có kết quả. Bạn có thể tải lại sau ít phút.</p>
        ) : null}
        {decision.status === "manual_review" ? (
          <p style={{ margin: 0 }}>Một chuyên viên sẽ xem hồ sơ của bạn. Bạn không cần nộp lại hồ sơ.</p>
        ) : null}
      </Card>
      {decision.reasons.length > 0 ? (
        <Card title="Những yếu tố ảnh hưởng nhiều nhất">
          <ReasonList reasons={decision.reasons} />
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Các yếu tố mô tả cách mô hình đánh giá hồ sơ, không phải nhận xét về cá nhân bạn. Hồ sơ không bao giờ bị
            từ chối chỉ vì hệ thống gặp sự cố.
          </p>
        </Card>
      ) : null}
      <Card title="Bạn có thể làm gì">
        <a href="/support" className="btn">Yêu cầu giải thích chi tiết hoặc khiếu nại</a>
      </Card>
    </div>
  );
}
