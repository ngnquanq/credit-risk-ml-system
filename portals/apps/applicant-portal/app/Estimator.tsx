"use client";

import { monthlyInstalment } from "@crs/api";
import { useState } from "react";

/** Illustrative annual rate; the real rate depends on the assessment. Replace with the published rate. */
const ILLUSTRATIVE_RATE_PCT = 20;
const vnd = new Intl.NumberFormat("vi-VN");

export function Estimator() {
  const [amount, setAmount] = useState(40_000_000);
  const [term, setTerm] = useState(24);
  const monthly = Math.round(monthlyInstalment(amount, term, ILLUSTRATIVE_RATE_PCT));

  return (
    <section className="card stack" aria-labelledby="est-title">
      <h2 id="est-title" style={{ margin: 0 }}>Ước tính khoản vay</h2>
      <div className="field">
        <label htmlFor="amount">Số tiền cần vay: <strong style={{ color: "var(--red)" }}>{vnd.format(amount)} ₫</strong></label>
        <input id="amount" type="range" min={3_000_000} max={100_000_000} step={1_000_000} value={amount}
          onChange={(e) => setAmount(Number(e.target.value))} style={{ accentColor: "var(--red)" }} />
      </div>
      <div className="field">
        <label htmlFor="term">Kỳ hạn: <strong style={{ color: "var(--red)" }}>{term} tháng</strong></label>
        <input id="term" type="range" min={6} max={36} step={1} value={term}
          onChange={(e) => setTerm(Number(e.target.value))} style={{ accentColor: "var(--red)" }} />
      </div>
      <div className="card" style={{ background: "var(--red-tint)" }}>
        <div className="muted">Tiền góp mỗi tháng (ước tính)</div>
        <div style={{ fontSize: 32, fontWeight: 700, color: "var(--red)" }} aria-live="polite">{vnd.format(monthly)} ₫</div>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Lãi suất minh hoạ {ILLUSTRATIVE_RATE_PCT}%/năm. Đây chưa phải đề nghị cho vay.
      </p>
      <a className="btn btn-primary" href={`/apply?amount=${amount}&term=${term}`}>Bắt đầu hồ sơ</a>
    </section>
  );
}
