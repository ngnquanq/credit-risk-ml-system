import { requireSession } from "@crs/auth/server";
import { Card } from "@crs/ui";

export default async function AlreadyApplied() {
  await requireSession("staff", ["loan_officer"]);
  return (
    <Card title="This customer already has an application">
      <p style={{ margin: 0 }}>
        One open application per customer. Ask the customer for their application reference (it starts with HS-) or
        check the status they see in the applicant portal.
      </p>
      <a className="btn" href="/applications/new" style={{ alignSelf: "flex-start" }}>Back to the form</a>
    </Card>
  );
}
