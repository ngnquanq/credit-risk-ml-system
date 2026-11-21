import "@crs/ui/tokens.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "CRS Lending", description: "Vay tiêu dùng, biết trước số tiền góp" };

export default function RootLayout({ children }: { children: ReactNode }) {
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
        <header style={{ background: "var(--white)", borderBottom: "1px solid var(--grey-200)" }}>
          <div className="container row" style={{ paddingTop: 12, paddingBottom: 12, justifyContent: "space-between" }}>
            <a href="/" className="row" style={{ color: "var(--black)", textDecoration: "none", fontWeight: 700 }}>
              <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
                <rect width="28" height="28" rx="8" fill="#C8102E" />
                <path d="M8 18 L13 10 L16 15 L20 9" stroke="#FFFFFF" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              CRS Lending
            </a>
            <nav className="row" aria-label="Tài khoản">
              <a href="/apply" className="btn btn-primary">Nộp hồ sơ</a>
              <a href="/auth/logout" className="btn">Đăng xuất</a>
            </nav>
          </div>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
