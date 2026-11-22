import { describe, expect, it } from "vitest";
import { caretAfterDigits, formatDateTimeVi, formatNumber, formatVnd, parseMoney, shortRef } from "./format";

describe("money format (comma every three digits)", () => {
  it("groups thousands with commas", () => {
    expect(formatVnd(40_000_000)).toBe("40,000,000 ₫");
    expect(formatNumber(2_035_832.4)).toBe("2,035,832");
    expect(formatNumber(999)).toBe("999");
  });

  it("parses what people type or paste", () => {
    expect(parseMoney("40,000,000 ₫")).toBe(40_000_000);
    expect(parseMoney("15.000.000")).toBe(15_000_000);
    expect(parseMoney("1e9")).toBe(19);
    expect(parseMoney("abc")).toBeNull();
    expect(parseMoney("")).toBeNull();
  });

  it("keeps the caret after the same digits when separators move", () => {
    // typing the 4th digit of 1234 -> "1,234": the caret goes after "4"
    expect(caretAfterDigits("1,234", 4)).toBe(5);
    // caret after the first digit of "12,345"
    expect(caretAfterDigits("12,345", 1)).toBe(1);
    // after 3 digits in "12,345" -> after "3", past the comma
    expect(caretAfterDigits("12,345", 3)).toBe(4);
    expect(caretAfterDigits("12,345", 0)).toBe(0);
  });
});

describe("references and dates", () => {
  it("shows a short reference instead of the full opaque id", () => {
    expect(shortRef("f0155e69-6681-49e9-86c0-6c92e99d27c9")).toBe("HS-F0155E69");
  });

  it("formats API timestamps (UTC without zone) as dd/mm/yyyy · hh:mm", () => {
    expect(formatDateTimeVi("2026-11-22T09:12:00")).toMatch(/^\d{2}\/\d{2}\/2026 · \d{2}:\d{2}$/);
    expect(formatDateTimeVi(null)).toBe("");
  });
});
