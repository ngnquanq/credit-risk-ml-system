import "@crs/ui/tokens.css";
import { optionalSession } from "@crs/auth/server";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "CRS Lending · Staff" };
export const dynamic = "force-dynamic";

// Navigation only shapes what each role sees; the API still checks every call (E11).
const NAV: { href: string; label: string; roles: string[] }[] = [
  { href: "/applications/new", label: "New application", roles: ["loan_officer"] },
  { href: "/reviews", label: "Review queue", roles: ["underwriter"] },
  { href: "/policy", label: "Decision policy", roles: ["risk_manager"] },
  { href: "/audit", label: "Decision trace", roles: ["auditor"] },
];

export default async function RootLayout({ children }: { children: ReactNode }) {
  const session = await optionalSession("staff");
  const links = NAV.filter((item) => session && item.roles.some((r) => session.roles.includes(r)));
  return (
    <html lang="en">
      <head>
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" />
      </head>
      <body>
        <header style={{ background: "var(--white)", borderBottom: "1px solid var(--grey-200)" }}>
          <div className="container row" style={{ paddingTop: 10, paddingBottom: 10, justifyContent: "space-between" }}>
            <div className="row" style={{ fontWeight: 700 }}>
              <svg width="26" height="26" viewBox="0 0 28 28" aria-hidden="true">
                <rect width="28" height="28" rx="8" fill="#C8102E" />
                <path d="M8 18 L13 10 L16 15 L20 9" stroke="#FFFFFF" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              CRS Lending · Staff
              {session?.branchId ? <span className="badge">Branch {session.branchId}</span> : null}
            </div>
            <nav className="row" aria-label="Main">
              {links.map((l) => (
                <a key={l.href} href={l.href} style={{ color: "var(--black)", minHeight: 44, display: "flex", alignItems: "center" }}>
                  {l.label}
                </a>
              ))}
              {session ? <a href="/auth/logout" className="btn">Sign out</a> : null}
            </nav>
          </div>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
