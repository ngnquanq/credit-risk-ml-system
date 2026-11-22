import { DOCUMENT_SLOTS, ILLUSTRATIVE_RATE_PCT, monthlyInstalment } from "@crs/api";
import { DEFAULT_DRAFT, type LoanDraft } from "@crs/auth";
import { readLoanDraft, requireSession } from "@crs/auth/server";
import { CsrfField, DocumentUpload, MoneyInput, Stepper, formatVnd } from "@crs/ui";
import { requestUpload, submitApplication } from "./actions";

export const dynamic = "force-dynamic";

const FLASH: Record<NonNullable<LoanDraft["flash"]>, string> = {
  exists: "Số CCCD này đã có hồ sơ đang xử lý. Vui lòng xem mục Hồ sơ của tôi hoặc liên hệ chi nhánh.",
  invalid: "Một số thông tin chưa hợp lệ. Vui lòng kiểm tra lại số CCCD, số điện thoại và ngày sinh.",
  documents: "Vui lòng tải lên lại ảnh CCCD hai mặt rồi gửi hồ sơ.",
  failed: "Chưa gửi được hồ sơ. Vui lòng thử lại sau ít phút.",
};

function Select({ id, label, options }: { id: string; label: string; options: [string, string][] }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} name={id} required>
        {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </div>
  );
}

export default async function ApplyPage() {
  const session = await requireSession("customers", ["applicant"]);
  const draft = (await readLoanDraft("customers")) ?? DEFAULT_DRAFT;
  const monthly = Math.round(monthlyInstalment(draft.amount, draft.term, ILLUSTRATIVE_RATE_PCT));

  return (
    <form action={submitApplication} className="stack">
      <CsrfField token={session.csrfToken} />
      <Stepper steps={["Ước tính", "Điền hồ sơ", "Nhận kết quả"]} current={1} />
      <h1 style={{ margin: 0 }}>Thông tin hồ sơ</h1>
      <p className="card mobile-only row" style={{ margin: 0, padding: "12px 16px", justifyContent: "space-between" }}>
        <span>Khoản vay: <strong className="amount">{formatVnd(draft.amount)}</strong> · {draft.term} tháng</span>
        <a href="/#estimator">Sửa</a>
      </p>
      {draft.flash ? <p className="alert" role="alert" style={{ margin: 0 }}>{FLASH[draft.flash]}</p> : null}

      <div className="layout-2col">
        <div className="stack">
          <section className="card stack" aria-labelledby="s-personal">
            <h2 id="s-personal" style={{ margin: 0, fontSize: 18 }}>Thông tin cá nhân</h2>
            <div className="form-grid">
              <div className="field" style={{ gridColumn: "1 / -1" }}>
                <label htmlFor="full_name">Họ và tên (theo CCCD)</label>
                <input id="full_name" name="full_name" autoComplete="name" required minLength={2} maxLength={120} />
              </div>
              <div className="field">
                <label htmlFor="citizen_id">Số CCCD</label>
                <input id="citizen_id" name="citizen_id" inputMode="numeric" autoComplete="off" required
                  pattern="\d{12}" maxLength={12} title="12 chữ số" aria-describedby="citizen_id-hint" />
                <span id="citizen_id-hint" className="muted" style={{ fontSize: 13 }}>12 chữ số, không gửi qua đường dẫn</span>
              </div>
              <div className="field">
                <label htmlFor="birth_date">Ngày sinh</label>
                <input id="birth_date" name="birth_date" type="date" autoComplete="bday" required />
              </div>
              <div className="field">
                <label htmlFor="phone">Số điện thoại</label>
                <input id="phone" name="phone" type="tel" inputMode="tel" autoComplete="tel" required
                  pattern="(\+?84|0)[\d ]{9,12}" title="Số di động Việt Nam, ví dụ 0912 345 678" />
              </div>
            </div>
          </section>

          <section className="card stack" aria-labelledby="s-work">
            <h2 id="s-work" style={{ margin: 0, fontSize: 18 }}>Công việc và thu nhập</h2>
            <div className="form-grid">
              <Select id="name_income_type" label="Nguồn thu nhập" options={[
                ["Working", "Làm công ăn lương"], ["Commercial associate", "Kinh doanh"],
                ["State servant", "Công chức"], ["Pensioner", "Hưu trí"],
              ]} />
              <div className="field">
                <label htmlFor="monthly_income">Thu nhập hằng tháng</label>
                <MoneyInput id="monthly_income" name="monthly_income" min={1_000_000} max={10_000_000_000} required />
              </div>
              <div className="field">
                <label htmlFor="employment_start_date">Bắt đầu công việc hiện tại</label>
                <input id="employment_start_date" name="employment_start_date" type="date" />
              </div>
            </div>
          </section>

          <section className="card stack" aria-labelledby="s-more">
            <h2 id="s-more" style={{ margin: 0, fontSize: 18 }}>Thông tin thêm</h2>
            <div className="form-grid">
              <Select id="name_education_type" label="Học vấn" options={[
                ["Secondary / secondary special", "Trung học"], ["Higher education", "Đại học"],
                ["Incomplete higher", "Đại học chưa hoàn thành"], ["Lower secondary", "Trung học cơ sở"],
              ]} />
              <Select id="name_family_status" label="Tình trạng hôn nhân" options={[
                ["Single / not married", "Độc thân"], ["Married", "Đã kết hôn"], ["Civil marriage", "Sống chung"],
                ["Separated", "Ly thân"], ["Widow", "Goá"],
              ]} />
              <Select id="name_housing_type" label="Nơi ở" options={[
                ["House / apartment", "Nhà riêng / căn hộ"], ["Rented apartment", "Thuê nhà"],
                ["With parents", "Ở cùng bố mẹ"], ["Municipal apartment", "Nhà công vụ"],
              ]} />
              <Select id="cnt_children" label="Số con" options={[["0", "0"], ["1", "1"], ["2", "2"], ["3", "3 trở lên"]]} />
            </div>
          </section>

          <section className="card stack" aria-labelledby="s-docs">
            <h2 id="s-docs" style={{ margin: 0, fontSize: 18 }}>Giấy tờ</h2>
            <p className="muted" style={{ margin: 0, fontSize: 14 }}>
              Ảnh được gửi thẳng tới kho lưu trữ có mã hoá, chỉ người xử lý hồ sơ xem được, và tự xoá sau 90 ngày.
            </p>
            <div className="form-grid">
              <DocumentUpload slot={DOCUMENT_SLOTS.idFront} label="CCCD mặt trước" required requestUpload={requestUpload} />
              <DocumentUpload slot={DOCUMENT_SLOTS.idBack} label="CCCD mặt sau" required requestUpload={requestUpload} />
            </div>
            <DocumentUpload slot={DOCUMENT_SLOTS.incomeProof} label="Sao kê lương 3 tháng"
              hint="Giúp duyệt nhanh hơn" requestUpload={requestUpload} />
          </section>
        </div>

        <aside className="stack">
          <section className="card stack desktop-only" aria-labelledby="s-loan">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2 id="s-loan" style={{ margin: 0, fontSize: 18 }}>Khoản vay của bạn</h2>
              <a href="/#estimator">Sửa</a>
            </div>
            <div className="summary-row"><span className="muted">Số tiền</span><strong data-testid="summary-amount">{formatVnd(draft.amount)}</strong></div>
            <div className="summary-row"><span className="muted">Kỳ hạn</span><strong>{draft.term} tháng</strong></div>
            <div className="summary-row"><span className="muted">Góp ước tính</span><strong>{formatVnd(monthly)}</strong></div>
          </section>

          <section className="card stack" aria-labelledby="s-consent">
            <h2 id="s-consent" style={{ margin: 0, fontSize: 18 }}>Đồng ý xử lý dữ liệu</h2>
            <label className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
              <input type="checkbox" name="bureau_consent" required style={{ width: 22, height: 22, flex: "none", accentColor: "var(--red)" }} />
              <span>Tôi đồng ý cho CRS Lending tra cứu thông tin tín dụng của tôi để đánh giá hồ sơ này.</span>
            </label>
            <button type="submit" className="btn btn-primary" style={{ justifyContent: "center" }}>Gửi hồ sơ</button>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              Hồ sơ không hỏi giới tính, dân tộc hay tôn giáo. Những thông tin này không được dùng để đánh giá.
            </p>
          </section>
        </aside>
      </div>
    </form>
  );
}
