"use client";

import type { MaskedApplicant, RevealedIdentity } from "@crs/api";
import { useState, type FormEvent } from "react";
import { revealIdentity } from "./actions";

/**
 * Name, masked citizen ID and phone. "Show" asks for a reason; the API audits it and the values
 * stay in this component's memory only (not in the URL, the page HTML or browser storage).
 */
export function CustomerIdentity({ applicationId, applicant, canReveal }: {
  applicationId: string;
  applicant: MaskedApplicant | null;
  canReveal: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revealed, setRevealed] = useState<RevealedIdentity | null>(null);

  if (!applicant) return <p className="muted" style={{ margin: 0 }}>No identity on record.</p>;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "");
    const result = await revealIdentity(applicationId, reason);
    setBusy(false);
    if (result.ok) {
      setRevealed(result.identity);
      setOpen(false);
    } else {
      setError(result.message);
    }
  }

  return (
    <div className="stack" style={{ gap: 10 }}>
      <table>
        <tbody>
          <tr><th scope="row">Name</th><td>{applicant.full_name}</td></tr>
          <tr><th scope="row">Citizen ID</th>
            <td className="masked" data-testid="citizen-id">{revealed ? revealed.citizen_id : applicant.citizen_id_masked}</td></tr>
          <tr><th scope="row">Phone</th>
            <td className="masked" data-testid="phone">{revealed ? revealed.phone : applicant.phone_masked}</td></tr>
        </tbody>
      </table>
      {revealed ? (
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span className="muted" style={{ fontSize: 12 }}>Shown for this view only. Your reason was logged.</span>
          <button type="button" className="btn" onClick={() => setRevealed(null)}>Hide</button>
        </div>
      ) : canReveal && !open ? (
        <button type="button" className="btn" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(true)}>
          Show citizen ID and phone
        </button>
      ) : null}
      {open ? (
        <form className="stack" style={{ gap: 8 }} onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="reveal-reason">Why do you need the full numbers?</label>
            <textarea id="reveal-reason" name="reason" rows={2} required minLength={10} maxLength={500}
              placeholder="e.g. customer at the counter, checking the ID card against the photo" />
          </div>
          {error ? <p className="error-text" role="alert" style={{ margin: 0 }}>{error}</p> : null}
          <div className="row">
            <button className="btn btn-primary" type="submit" disabled={busy}>Show</button>
            <button className="btn" type="button" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      ) : null}
      {!open && error ? <p className="error-text" role="alert" style={{ margin: 0 }}>{error}</p> : null}
    </div>
  );
}
