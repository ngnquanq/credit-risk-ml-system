"use client";

import { DOCUMENT_SLOTS } from "@crs/api";
import { DocumentUpload } from "@crs/ui";
import { attachDocument, requestUpload } from "../../apply/actions";

/** During manual review: payslips go to storage, then get attached to this application. */
export function PayslipUpload({ applicationId }: { applicationId: string }) {
  return (
    <DocumentUpload
      slot={DOCUMENT_SLOTS.incomeProof}
      label="Tải lên sao kê lương 3 tháng"
      hint="Giúp chuyên viên xác nhận thu nhập nhanh hơn"
      requestUpload={requestUpload}
      onUploaded={(documentId) => attachDocument(applicationId, DOCUMENT_SLOTS.incomeProof, documentId)}
    />
  );
}
