/**
 * Money is shown with a comma every three digits ("40,000,000 ₫"), as agreed for both portals.
 * Inputs never use type="number" for money: browsers drop the separators, accept "e", and change
 * the value on scroll (GOV.UK Design System guidance).
 */
const grouped = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatNumber(value: number): string {
  return grouped.format(Math.round(value));
}

export function formatVnd(value: number): string {
  return `${formatNumber(value)} ₫`;
}

/** Digits only; null when there are none. "40,000,000 ₫" -> 40000000. */
export function parseMoney(text: string): number | null {
  const digits = text.replace(/\D/g, "");
  if (!digits) return null;
  const value = Number(digits.slice(0, 15));
  return Number.isSafeInteger(value) ? value : null;
}

/** Keep the caret after the same number of digits when separators are inserted or removed. */
export function caretAfterDigits(formatted: string, digitsBefore: number): number {
  if (digitsBefore <= 0) return 0;
  let seen = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted.charAt(i))) seen++;
    if (seen === digitsBefore) return i + 1;
  }
  return formatted.length;
}

export function formatDateTimeVi(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} · ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Short, human-friendly reference for an opaque id (first 8 hex digits, upper case). */
export function shortRef(id: string): string {
  return `HS-${id.replace(/-/g, "").slice(0, 8).toUpperCase()}`;
}
