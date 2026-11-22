import "@crs/ui/tokens.css";
import { optionalSession } from "@crs/auth/server";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "CRS Lending", description: "Vay tiêu dùng, biết trước số tiền góp" };
export const dynamic = "force-dynamic";

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect width="28" height="28" rx="8" fill="#C8102E" />
      <path d="M8 18 L13 10 L16 15 L20 9" stroke="#FFFFFF" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const session = await optionalSession("customers").catch(() => null);
  return (
    <html lang="vi">
      <head>
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap"
        />
      </head>
      <body style={{ fontFamily: "var(--font-vi)" }}>
        <header className="site-header">
          <div className="container">
            <a href="/" className="brand" aria-label="CRS Lending"><Logo /><span className="brand-name">CRS Lending</span></a>
            <nav className="site-nav" aria-label="Tài khoản">
              {session ? (
                <>
                  <a href="/applications" className="nav-link">Hồ sơ của tôi</a>
                  {session.name ? <span className="muted hide-sm" style={{ fontSize: 14 }}>{session.name}</span> : null}
                  <a href="/auth/logout" className="btn">Đăng xuất</a>
                </>
              ) : (
                <>
                  <a href="/auth/login?returnTo=%2Fapplications" className="nav-link">Đăng nhập</a>
                  <a href="/#estimator" className="btn btn-primary hide-sm">Nộp hồ sơ</a>
                </>
              )}
            </nav>
          </div>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
