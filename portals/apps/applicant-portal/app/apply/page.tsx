import { paths, type ApplicationInput } from "@crs/api";
import { ApiError, api, assertMutation, requireSession } from "@crs/auth/server";
import { CsrfField } from "@crs/ui";
import { redirect } from "next/navigation";

async function submit(form: FormData) {
  "use server";
  const session = await requireSession("customers", ["applicant"]);
  assertMutation("customers", session, form);
  const id = String(form.get("sk_id_curr") ?? "").trim();
  const body: ApplicationInput = {
    sk_id_curr: id,
    birth_date: String(form.get("birth_date")),
    cnt_children: 0,
    amt_income_total: Number(form.get("amt_income_total")) * 12,
    amt_credit: Number(form.get("amt_credit")),
    amt_goods_price: Number(form.get("amt_credit")),
    name_income_type: String(form.get("name_income_type")),
    name_education_type: String(form.get("name_education_type")),
    name_family_status: "Single / not married",
    name_housing_type: "House / apartment",
    employment_start_date: (form.get("employment_start_date") as string) || undefined,
    bureau_consent: form.get("bureau_consent") === "on",
  };
  try {
    // Ownership (channel=self, applicant_sub) is set by the API from the token, never from this body.
    await api("customers", session, paths.applications, { method: "POST", body: JSON.stringify(body) });
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) redirect(`/applications/${encodeURIComponent(id)}`);
    throw error;
  }
  redirect(`/applications/${encodeURIComponent(id)}`);
}

export default async function ApplyPage({ searchParams }: { searchParams: { amount?: string } }) {
  const session = await requireSession("customers", ["applicant"]);
  const amount = Number(searchParams.amount ?? 40_000_000);

  return (
    <form action={submit} className="stack" style={{ maxWidth: 760 }}>
      <CsrfField token={session.csrfToken} />
      <h1 style={{ margin: 0 }}>Thông tin hồ sơ</h1>

      <section className="card stack">
        <h2 style={{ margin: 0, fontSize: 18 }}>Khoản vay</h2>
        <div className="field">
          <label htmlFor="amt_credit">Số tiền cần vay (₫)</label>
          <input id="amt_credit" name="amt_credit" type="number" min={3000000} max={100000000} step={1000000} defaultValue={amount} required />
        </div>
      </section>

      <section className="card stack">
        <h2 style={{ margin: 0, fontSize: 18 }}>Thông tin cá nhân</h2>
        <div className="grid">
          <div className="field">
            <label htmlFor="sk_id_curr">Mã khách hàng</label>
            <input id="sk_id_curr" name="sk_id_curr" required pattern="[A-Za-z0-9_-]{1,32}" />
          </div>
          <div className="field">
            <label htmlFor="birth_date">Ngày sinh</label>
            <input id="birth_date" name="birth_date" type="date" required />
          </div>
        </div>
      </section>

      <section className="card stack">
        <h2 style={{ margin: 0, fontSize: 18 }}>Công việc và thu nhập</h2>
        <div className="grid">
          <div className="field">
            <label htmlFor="name_income_type">Nguồn thu nhập</label>
            <select id="name_income_type" name="name_income_type" required>
              <option value="Working">Làm công ăn lương</option>
              <option value="Commercial associate">Kinh doanh</option>
              <option value="Pensioner">Hưu trí</option>
              <option value="State servant">Công chức</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="amt_income_total">Thu nhập hằng tháng (₫)</label>
            <input id="amt_income_total" name="amt_income_total" type="number" min={1} required />
          </div>
          <div className="field">
            <label htmlFor="employment_start_date">Bắt đầu công việc hiện tại</label>
            <input id="employment_start_date" name="employment_start_date" type="date" />
          </div>
          <div className="field">
            <label htmlFor="name_education_type">Học vấn</label>
            <select id="name_education_type" name="name_education_type" required>
              <option value="Secondary / secondary special">Trung học</option>
              <option value="Higher education">Đại học</option>
              <option value="Incomplete higher">Đại học chưa hoàn thành</option>
            </select>
          </div>
        </div>
      </section>

      <section className="card stack">
        <h2 style={{ margin: 0, fontSize: 18 }}>Đồng ý xử lý dữ liệu</h2>
        <label className="row" style={{ alignItems: "flex-start" }}>
          <input type="checkbox" name="bureau_consent" required style={{ width: 22, height: 22, accentColor: "var(--red)" }} />
          <span>Tôi đồng ý cho CRS Lending tra cứu thông tin tín dụng của tôi để đánh giá hồ sơ này.</span>
        </label>
      </section>

      <button type="submit" className="btn btn-primary">Gửi hồ sơ</button>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Hồ sơ không hỏi giới tính, dân tộc hay tôn giáo. Những thông tin này không được dùng để đánh giá.
      </p>
    </form>
  );
}
