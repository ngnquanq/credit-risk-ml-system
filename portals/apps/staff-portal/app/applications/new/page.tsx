import { paths, type ApplicationInput } from "@crs/api";
import { api, assertMutation, requireSession } from "@crs/auth/server";
import { Card, CsrfField } from "@crs/ui";
import { redirect } from "next/navigation";

async function submit(form: FormData) {
  "use server";
  const session = await requireSession("staff", ["loan_officer"]);
  assertMutation("staff", session, form);
  const id = String(form.get("sk_id_curr") ?? "").trim();
  const body: ApplicationInput = {
    sk_id_curr: id,
    birth_date: String(form.get("birth_date")),
    cnt_children: Number(form.get("cnt_children") ?? 0),
    amt_income_total: Number(form.get("amt_income_total")),
    amt_credit: Number(form.get("amt_credit")),
    amt_goods_price: Number(form.get("amt_goods_price") || form.get("amt_credit")),
    name_income_type: String(form.get("name_income_type")),
    name_education_type: String(form.get("name_education_type")),
    name_family_status: String(form.get("name_family_status")),
    name_housing_type: String(form.get("name_housing_type")),
    employment_start_date: (form.get("employment_start_date") as string) || undefined,
    organization_type: (form.get("organization_type") as string) || undefined,
    bureau_consent: form.get("bureau_consent") === "on",
  };
  // channel=staff, created_by_sub and branch_id come from the officer's token (E11).
  await api("staff", session, paths.applications, { method: "POST", body: JSON.stringify(body) });
  redirect(`/cases/${encodeURIComponent(id)}`);
}

export default async function NewApplication() {
  const session = await requireSession("staff", ["loan_officer"]);
  return (
    <form action={submit} className="stack" style={{ maxWidth: 980 }}>
      <CsrfField token={session.csrfToken} />
      <h1 style={{ margin: 0 }}>New application · walk-in customer</h1>
      <Card title="Customer">
        <div className="grid">
          <div className="field"><label htmlFor="sk_id_curr">Customer ID</label><input id="sk_id_curr" name="sk_id_curr" required pattern="[A-Za-z0-9_-]{1,32}" /></div>
          <div className="field"><label htmlFor="birth_date">Date of birth</label><input id="birth_date" name="birth_date" type="date" required /></div>
          <div className="field"><label htmlFor="cnt_children">Children</label><input id="cnt_children" name="cnt_children" type="number" min={0} defaultValue={0} /></div>
          <div className="field">
            <label htmlFor="name_family_status">Family status</label>
            <select id="name_family_status" name="name_family_status">
              <option>Married</option><option>Single / not married</option><option>Civil marriage</option><option>Separated</option><option>Widow</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="name_housing_type">Housing</label>
            <select id="name_housing_type" name="name_housing_type">
              <option>House / apartment</option><option>With parents</option><option>Rented apartment</option><option>Municipal apartment</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="name_education_type">Education</label>
            <select id="name_education_type" name="name_education_type">
              <option>Secondary / secondary special</option><option>Higher education</option><option>Incomplete higher</option><option>Lower secondary</option>
            </select>
          </div>
        </div>
      </Card>
      <Card title="Employment and income">
        <div className="grid">
          <div className="field">
            <label htmlFor="name_income_type">Income type</label>
            <select id="name_income_type" name="name_income_type">
              <option>Working</option><option>Commercial associate</option><option>Pensioner</option><option>State servant</option>
            </select>
          </div>
          <div className="field"><label htmlFor="amt_income_total">Annual income (₫)</label><input id="amt_income_total" name="amt_income_total" type="number" min={1} required /></div>
          <div className="field"><label htmlFor="employment_start_date">Current job since</label><input id="employment_start_date" name="employment_start_date" type="date" /></div>
          <div className="field"><label htmlFor="organization_type">Employer sector</label><input id="organization_type" name="organization_type" /></div>
        </div>
      </Card>
      <Card title="Loan">
        <div className="grid">
          <div className="field"><label htmlFor="amt_credit">Credit amount (₫)</label><input id="amt_credit" name="amt_credit" type="number" min={1} required /></div>
          <div className="field"><label htmlFor="amt_goods_price">Goods price (₫)</label><input id="amt_goods_price" name="amt_goods_price" type="number" min={0} /></div>
        </div>
        <label className="row">
          <input type="checkbox" name="bureau_consent" required style={{ width: 20, height: 20, accentColor: "var(--red)" }} />
          The customer consented to the credit bureau check
        </label>
      </Card>
      <button className="btn btn-primary" type="submit">Submit application</button>
    </form>
  );
}
