"use client";

import { useRef, useState, type ChangeEvent } from "react";

export interface UploadTicket {
  upload_url: string;
  fields: Record<string, string>;
  document_id: string;
  max_bytes: number;
}

/** Server action that asks the API for a one-object upload policy (the BFF relays the user's token). */
export type RequestUpload = (slot: number, contentType: string) => Promise<UploadTicket>;

const ACCEPT = ["image/jpeg", "image/png", "application/pdf"];

interface Props {
  slot: number;
  label: string;
  hint?: string;
  required?: boolean;
  requestUpload: RequestUpload;
  /** Called with the document id once storage has the file (e.g. to attach it right away). */
  onUploaded?: (documentId: string) => Promise<void> | void;
}

type State = { kind: "idle" } | { kind: "uploading"; name: string } | { kind: "done"; name: string } | { kind: "error"; message: string };

/**
 * Browser -> storage upload with a presigned POST policy: the file never passes through the
 * portal or the API, and the policy only allows this one object, type and size.
 * The document id goes to the form in a field named document_id_<slot>.
 */
export function DocumentUpload({ slot, label, hint, required, requestUpload, onUploaded }: Props) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [documentId, setDocumentId] = useState("");
  const carrier = useRef<HTMLInputElement>(null);
  const inputId = `doc-${slot}`;

  async function onChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!ACCEPT.includes(file.type)) {
      setState({ kind: "error", message: "Chỉ nhận ảnh JPG, PNG hoặc tệp PDF." });
      return;
    }
    setState({ kind: "uploading", name: file.name });
    try {
      const ticket = await requestUpload(slot, file.type);
      if (file.size > ticket.max_bytes) {
        setState({ kind: "error", message: `Tệp lớn hơn ${Math.round(ticket.max_bytes / 1024 / 1024)} MB.` });
        return;
      }
      const body = new FormData();
      for (const [key, value] of Object.entries(ticket.fields)) body.append(key, value);
      body.append("file", file); // the file must be the last field of a POST policy upload
      const response = await fetch(ticket.upload_url, { method: "POST", body });
      if (!response.ok) throw new Error(`storage ${response.status}`);
      await onUploaded?.(ticket.document_id);
      setDocumentId(ticket.document_id);
      carrier.current?.setCustomValidity("");
      setState({ kind: "done", name: file.name });
    } catch {
      setDocumentId("");
      setState({ kind: "error", message: "Tải lên chưa được. Vui lòng thử lại." });
    }
  }

  return (
    <div className={`upload ${state.kind === "done" ? "upload-done" : ""}`}>
      <label htmlFor={inputId} className="upload-label">
        <span className="upload-icon" aria-hidden="true">{state.kind === "done" ? "✓" : "↑"}</span>
        <span className="stack" style={{ gap: 2 }}>
          <strong>{label}{required ? "" : " (không bắt buộc)"}</strong>
          <span className="muted" style={{ fontSize: 13 }} aria-live="polite">
            {state.kind === "idle" && (hint ?? "Bấm để chọn ảnh hoặc tệp PDF, tối đa 10 MB")}
            {state.kind === "uploading" && `Đang tải lên ${state.name}…`}
            {state.kind === "done" && `Đã tải lên · ${state.name}`}
            {state.kind === "error" && <span className="error-text">{state.message}</span>}
          </span>
        </span>
      </label>
      <input id={inputId} type="file" accept={ACCEPT.join(",")} onChange={onChange} className="visually-hidden"
        data-testid={`upload-${slot}`} />
      {/* Carries the id to the form; `required` makes the browser stop a submit without the file. */}
      <input
        ref={carrier}
        className="visually-hidden"
        tabIndex={-1}
        aria-hidden="true"
        name={`document_id_${slot}`}
        value={documentId}
        required={required}
        onChange={() => undefined}
        onInvalid={(e) => e.currentTarget.setCustomValidity(`Vui lòng tải lên: ${label}`)}
      />
    </div>
  );
}
