import { requireSession } from "@crs/auth/server";
import { redirect } from "next/navigation";

const HOME: [string, string][] = [
  ["loan_officer", "/applications/new"],
  ["underwriter", "/reviews"],
  ["risk_manager", "/policy"],
  ["auditor", "/audit"],
];

export default async function Home() {
  const session = await requireSession("staff");
  const target = HOME.find(([role]) => session.roles.includes(role));
  redirect(target ? target[1] : "/forbidden");
}
