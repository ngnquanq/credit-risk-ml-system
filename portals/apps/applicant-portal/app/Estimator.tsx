"use client";

import { ILLUSTRATIVE_RATE_PCT, monthlyInstalment } from "@crs/api";
import { formatVnd } from "@crs/ui";
import { useState } from "react";
import { startApplication } from "./actions";

export function Estimator({ initialAmount, initialTerm }: { initialAmount: number; initialTerm: number }) {
  const [amount, setAmount] = useState(initialAmount);
  const [term, setTerm] = useState(initialTerm);
  const monthly = Math.round(monthlyInstalment(amount, term, ILLUSTRATIVE_RATE_PCT));

  return (
    <form action={startApplication} className="card stack" aria-labelledby="est-title" id="estimator">
      <h2 id="est-title" style={{ margin: 0 }}>Ước tính khoản vay</h2>
      <div className="field">
        <label htmlFor="amount">
          Số tiền cần vay: <strong className="amount" style={{ color: "var(--red)" }} data-testid="amount">{formatVnd(amount)}</strong>
        </label>
        <input id="amount" name="amount" type="range" min={3_000_000} max={100_000_000} step={1_000_000} value={amount}
          onChange={(e) => setAmount(Number(e.target.value))} style={{ accentColor: "var(--red)" }}
          aria-valuetext={formatVnd(amount)} />
        <div className="row muted" style={{ justifyContent: "space-between", fontSize: 13 }}><span>3 triệu</span><span>100 triệu</span></div>
      </div>
      <div className="field">
        <label htmlFor="term">Kỳ hạn: <strong style={{ color: "var(--red)" }}>{term} tháng</strong></label>
        <input id="term" name="term" type="range" min={6} max={36} step={1} value={term}
          onChange={(e) => setTerm(Number(e.target.value))} style={{ accentColor: "var(--red)" }}
          aria-valuetext={`${term} tháng`} />
        <div className="row muted" style={{ justifyContent: "space-between", fontSize: 13 }}><span>6 tháng</span><span>36 tháng</span></div>
      </div>
      <div className="card" style={{ background: "var(--red-tint)" }}>
        <div className="muted">Tiền góp mỗi tháng (ước tính)</div>
        <div className="amount" style={{ fontSize: 32, fontWeight: 700, color: "var(--red)" }} aria-live="polite" data-testid="monthly">
          {formatVnd(monthly)}
        </div>
      </div>
      <button type="submit" className="btn btn-primary" style={{ justifyContent: "center" }}>Bắt đầu hồ sơ</button>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Lãi suất minh hoạ {ILLUSTRATIVE_RATE_PCT}%/năm. Đây chưa phải đề nghị cho vay; lãi suất thực tế phụ thuộc kết quả đánh giá.
      </p>
    </form>
  );
}
