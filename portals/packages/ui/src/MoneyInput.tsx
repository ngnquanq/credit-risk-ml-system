"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { caretAfterDigits, formatNumber, parseMoney } from "./format";

interface Props {
  id: string;
  /** Name of the hidden field that carries the plain number to the server. */
  name: string;
  defaultValue?: number;
  min?: number;
  max?: number;
  required?: boolean;
  describedBy?: string;
}

/** Text input that groups digits with commas while typing and submits the plain number. */
export function MoneyInput({ id, name, defaultValue, min, max, required, describedBy }: Props) {
  const [value, setValue] = useState<number | null>(defaultValue ?? null);
  const input = useRef<HTMLInputElement>(null);

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const el = event.target;
    const digitsBefore = el.value.slice(0, el.selectionStart ?? el.value.length).replace(/\D/g, "").length;
    const next = parseMoney(el.value);
    setValue(next);
    const text = next === null ? "" : formatNumber(next);
    el.value = text;
    const caret = caretAfterDigits(text, digitsBefore);
    el.setSelectionRange(caret, caret);

    let message = "";
    if (next !== null && min !== undefined && next < min) message = `Tối thiểu ${formatNumber(min)} ₫`;
    if (next !== null && max !== undefined && next > max) message = `Tối đa ${formatNumber(max)} ₫`;
    el.setCustomValidity(message);
  }

  return (
    <div className="money-input">
      <input
        ref={input}
        id={id}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        defaultValue={defaultValue === undefined ? "" : formatNumber(defaultValue)}
        onChange={onChange}
        required={required}
        aria-describedby={describedBy}
      />
      <span className="money-suffix" aria-hidden="true">₫</span>
      <input type="hidden" name={name} value={value ?? ""} />
    </div>
  );
}
