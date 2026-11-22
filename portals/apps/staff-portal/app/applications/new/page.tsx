import { DOCUMENT_SLOTS, paths, type ApplicationInput } from "@crs/api";
import { ApiError, api, assertMutation, requireSession } from "@crs/auth/server";
import { Card, CsrfField, DocumentUpload, MoneyInput } from "@crs/ui";
import { redirect } from "next/navigation";
import { requestUpload } from "../../actions";

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

async function submit(form: FormData) {
  "use server";
  const session = await requireSession("staff", ["loan_officer"]);
  assertMutation("staff", session, form);
  const documentIds: Record<string, string> = {};
  for (const slot of Object.values(DOCUMENT_SLOTS)) {
    const id = text(form, `document_id_${slot}`);
    if (id) documentIds[`document_id_${slot}`] = id;
  }
  const body: ApplicationInput = {
    applicant: { full_name: text(form, "full_name"), citizen_id: text(form, "citizen_id"), phone: text(form, "phone") },
    birth_date: text(form, "birth_date"),
    cnt_children: Number(text(form, "cnt_children") || 0),
    amt_income_total: Number(text(form, "amt_income_total")),
    amt_credit: Number(text(form, "amt_credit")),
    amt_goods_price: Number(text(form, "amt_goods_price") || text(form, "amt_credit")),
    name_income_type: text(form, "name_income_type"),
    name_education_type: text(form, "name_education_type"),
    name_family_status: text(form, "name_family_status"),
    name_housing_type: text(form, "name_housing_type"),
    employment_start_date: text(form, "employment_start_date") || undefined,
    organization_type: text(form, "organization_type") || undefined,
    document_ids: documentIds,
    bureau_consent: form.get("bureau_consent") === "on",
  };
  let created: { id: string };
  try {
    // channel=staff, created_by_sub and branch_id come from the officer's token (E11);
    // the customer key comes from the citizen ID, so returning customers keep their history.
    created = await api<{ id: string }>("staff", session, paths.applications, { method: "POST", body: JSON.stringify(body) });
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) redirect("/applications/new/exists");
    throw error;
  }
  redirect(`/cases/${encodeURIComponent(created.id)}`);
}

export default async function NewApplication() {
  const session = await requireSession("staff", ["loan_officer"]);
  return (
    <form action={submit} className="stack" style={{ maxWidth: 980 }}>
      <CsrfField token={session.csrfToken} />
      <h1 style={{ margin: 0 }}>New application · walk-in customer</h1>
      <Card title="Customer identity">
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Check the physical ID card. The citizen ID and phone are stored encrypted and shown masked afterwards.
        </p>
        <div className="grid">
          <div className="field"><label htmlFor="full_name">Full name (as on the ID card)</label>
            <input id="full_name" name="full_name" required minLength={2} maxLength={120} autoComplete="off" /></div>
          <div className="field"><label htmlFor="citizen_id">Citizen ID (CCCD)</label>
            <input id="citizen_id" name="citizen_id" required inputMode="numeric" pattern="\d{12}" maxLength={12} title="12 digits" autoComplete="off" /></div>
          <div className="field"><label htmlFor="phone">Mobile phone</label>
            <input id="phone" name="phone" type="tel" required pattern="(\+?84|0)[\d ]{9,12}" autoComplete="off" /></div>
          <div className="field"><label htmlFor="birth_date">Date of birth</label><input id="birth_date" name="birth_date" type="date" required /></div>
        </div>
        <div className="grid">
          <DocumentUpload slot={DOCUMENT_SLOTS.idFront} label="ID card, front" hint="Scan or photo" requestUpload={requestUpload} />
          <DocumentUpload slot={DOCUMENT_SLOTS.idBack} label="ID card, back" hint="Scan or photo" requestUpload={requestUpload} />
        </div>
      </Card>
      <Card title="Household">
        <div className="grid">
          <div className="field">
            <label htmlFor="cnt_children">Children</label>
            <select id="cnt_children" name="cnt_children"><option>0</option><option>1</option><option>2</option><option value="3">3 or more</option></select>
          </div>
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
          <div className="field"><label htmlFor="amt_income_total">Annual income</label>
            <MoneyInput id="amt_income_total" name="amt_income_total" min={1} required /></div>
          <div className="field"><label htmlFor="employment_start_date">Current job since</label><input id="employment_start_date" name="employment_start_date" type="date" /></div>
          <div className="field"><label htmlFor="organization_type">Employer sector</label><input id="organization_type" name="organization_type" /></div>
        </div>
        <DocumentUpload slot={DOCUMENT_SLOTS.incomeProof} label="Payslips or salary statement" requestUpload={requestUpload} />
      </Card>
      <Card title="Loan">
        <div className="grid">
          <div className="field"><label htmlFor="amt_credit">Credit amount</label>
            <MoneyInput id="amt_credit" name="amt_credit" min={1_000_000} required /></div>
          <div className="field"><label htmlFor="amt_goods_price">Goods price</label>
            <MoneyInput id="amt_goods_price" name="amt_goods_price" /></div>
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
