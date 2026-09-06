/**
 * The only module permitted to convert an API numeric string.
 *
 * The backend sends money, percentages and quantities as decimal STRINGS with
 * fixed precision (amounts 2dp, unit prices 4dp, percentages 4dp, quantities
 * 4dp, proration 8dp). `Number("132710.00")` silently enters float territory
 * and 0.1 + 0.2 territory with it, so every arithmetic path goes through
 * Decimal and every display path goes through a formatter here.
 *
 * ESLint forbids parseFloat / Number() / unary + on API values elsewhere.
 */
import Decimal from "decimal.js-light";

Decimal.set({ precision: 28, rounding: Decimal.ROUND_HALF_UP });

export type Numeric = string | number | null | undefined;

export const dec = (v: Numeric): Decimal => {
  if (v === null || v === undefined || v === "") return new Decimal(0);
  return new Decimal(String(v));
};

export const isZero = (v: Numeric) => dec(v).isZero();
export const isNeg = (v: Numeric) => dec(v).isNegative();
export const cmp = (a: Numeric, b: Numeric) => dec(a).comparedTo(dec(b));
export const sub = (a: Numeric, b: Numeric) => dec(a).minus(dec(b)).toString();
export const add = (a: Numeric, b: Numeric) => dec(a).plus(dec(b)).toString();

/** Signed difference as a display string, e.g. "+8,400.00" / "−8,400.00". */
export const delta = (from: Numeric, to: Numeric): string => {
  const d = dec(to).minus(dec(from));
  const sign = d.isNegative() ? "\u2212" : d.isZero() ? "" : "+";
  return sign + group(d.abs().toFixed(2));
};

const group = (s: string): string => {
  const [whole, frac] = s.split(".");
  const sign = whole.startsWith("-") ? "-" : "";
  const digits = sign ? whole.slice(1) : whole;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return sign + grouped + (frac ? `.${frac}` : "");
};

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$", EUR: "\u20ac", GBP: "\u00a3", INR: "\u20b9", JPY: "\u00a5",
};

export const currencySymbol = (code = "USD") => CURRENCY_SYMBOL[code] ?? "";

/** 132710.00 -> "132,710.00" (no symbol; the symbol is rendered separately
 *  so it can be de-emphasised next to the figure). */
export const formatAmount = (v: Numeric, dp = 2): string => group(dec(v).toFixed(dp));

/** 132710.00 -> "$132,710.00" */
export const formatMoney = (v: Numeric, currency = "USD", dp = 2): string =>
  `${currencySymbol(currency)}${formatAmount(v, dp)}`;

/** 132710.00 -> "$132.7k" for tight spaces such as Kanban cards. */
export const formatCompact = (v: Numeric, currency = "USD"): string => {
  const d = dec(v);
  const abs = d.abs();
  const sym = currencySymbol(currency);
  const sign = d.isNegative() ? "\u2212" : "";
  if (abs.gte(1_000_000)) return `${sign}${sym}${abs.div(1_000_000).toFixed(2)}M`;
  if (abs.gte(1_000)) return `${sign}${sym}${abs.div(1_000).toFixed(1)}k`;
  return `${sign}${sym}${abs.toFixed(0)}`;
};

/** "24.4970" -> "24.50%" (display 2dp; the underlying 4dp is preserved). */
export const formatPct = (v: Numeric, dp = 2): string => `${dec(v).toFixed(dp)}%`;

/** Full precision, for tooltips and the audit trail. */
export const formatExact = (v: Numeric): string => dec(v).toString();

/** "100.0000" -> "100"; "1.5000" -> "1.5" */
export const formatQty = (v: Numeric): string => {
  const s = dec(v).toFixed(4).replace(/\.?0+$/, "");
  return group(s === "" || s === "-" ? "0" : s);
};

/** "32.4440" -> "32.4" — risk scores read better at 1dp. */
export const formatScore = (v: Numeric, dp = 1): string => dec(v).toFixed(dp);

/**
 * A float, for SORTING ONLY.
 *
 * Comparators need a primitive and never feed a displayed value, so the
 * precision loss is harmless here — and confined to this one named function
 * rather than scattered `Number(...)` calls that look like arithmetic.
 */
export const sortKey = (v: Numeric): number => dec(v).toNumber();

/** Band a blended-risk score exactly as the backend does. */
export const riskBandFor = (score: Numeric): "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" => {
  const d = dec(score);
  if (d.gte(75)) return "CRITICAL";
  if (d.gte(50)) return "HIGH";
  if (d.gte(25)) return "MEDIUM";
  if (d.gt(0)) return "LOW";
  return "NONE";
};

/* -- dates ---------------------------------------------------------------- */
export const formatDate = (iso?: string | null): string =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "\u2014";

export const formatDateTime = (iso?: string | null): string =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : "\u2014";

export const formatRelative = (iso?: string | null): string => {
  if (!iso) return "\u2014";
  const then = new Date(iso).getTime();
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
};
