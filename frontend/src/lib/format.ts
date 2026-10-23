const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** 10000 -> "$10,000.00", -12.5 -> "-$12.50". */
export function formatMoney(value: number): string {
  return usd.format(normalizeZero(value));
}

/** Like formatMoney, with an explicit sign: "+$10.80", "-$5.00", "$0.00". */
export function formatSignedMoney(value: number): string {
  const v = normalizeZero(round(value, 2));
  if (v > 0) return `+${usd.format(v)}`;
  return usd.format(v);
}

/** A price without the currency symbol: 190.1 -> "190.10". */
export function formatPrice(value: number): string {
  return normalizeZero(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** 0.333 -> "+0.33%", -1 -> "-1.00%", 0 -> "0.00%". */
export function formatPercent(value: number): string {
  const v = normalizeZero(round(value, 2));
  const body = `${Math.abs(v).toFixed(2)}%`;
  if (v > 0) return `+${body}`;
  if (v < 0) return `-${body}`;
  return body;
}

/** Share quantities keep up to 4 decimals without trailing zeros: 10 -> "10", 0.5 -> "0.5". */
export function formatQuantity(value: number): string {
  return normalizeZero(value).toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  });
}

export function round(value: number, digits: number): number {
  const f = 10 ** digits;
  return Math.round(value * f) / f;
}

/** Avoid rendering "-0.00". */
function normalizeZero(value: number): number {
  return Object.is(value, -0) || Math.abs(value) < 1e-9 ? 0 : value;
}

export type PnlSign = "positive" | "negative" | "zero";

/** "positive" | "negative" | "zero", judged at 2-decimal precision so the label matches the text. */
export function pnlSign(value: number): PnlSign {
  const v = round(value, 2);
  if (v > 0) return "positive";
  if (v < 0) return "negative";
  return "zero";
}
