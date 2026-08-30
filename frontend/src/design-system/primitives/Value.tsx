/**
 * Numeric display primitives.
 *
 * Everything financial goes through here so that (a) no component ever calls
 * Number() on an API string, and (b) every figure gets tabular numerals and
 * therefore aligns on the decimal down a column.
 */
import * as React from "react";
import { cn } from "@/lib/cn";
import {
  currencySymbol, dec, formatAmount, formatCompact, formatExact,
  formatPct, formatQty, formatScore, type Numeric,
} from "@/api/money";

/* -- Money ---------------------------------------------------------------- */
export function Money({
  value, currency = "USD", className, compact, dp = 2, showSymbol = true, signed, style,
}: {
  value: Numeric; currency?: string; className?: string; compact?: boolean;
  dp?: number; showSymbol?: boolean; signed?: boolean; style?: React.CSSProperties;
}) {
  const d = dec(value);
  const sign = signed ? (d.isNegative() ? "\u2212" : d.isZero() ? "" : "+") : d.isNegative() ? "\u2212" : "";
  const body = compact
    ? formatCompact(d.abs().toString(), showSymbol ? currency : "")
    : formatAmount(d.abs().toString(), dp);
  return (
    <span className={cn("num whitespace-nowrap", className)} style={style} title={formatExact(value)}>
      {sign}
      {showSymbol && !compact && (
        <span className="text-content-faint">{currencySymbol(currency)}</span>
      )}
      {body}
    </span>
  );
}

/* -- Percent -------------------------------------------------------------- */
export function Percent({
  value, className, dp = 2, signed, style,
}: { value: Numeric; className?: string; dp?: number; signed?: boolean; style?: React.CSSProperties }) {
  const d = dec(value);
  const sign = signed ? (d.isNegative() ? "\u2212" : d.isZero() ? "" : "+") : d.isNegative() ? "\u2212" : "";
  return (
    <span className={cn("num whitespace-nowrap", className)} style={style} title={`${formatExact(value)}%`}>
      {sign}{formatPct(d.abs().toString(), dp)}
    </span>
  );
}

/* -- Quantity ------------------------------------------------------------- */
export function Qty({ value, className, style }: { value: Numeric; className?: string; style?: React.CSSProperties }) {
  return (
    <span className={cn("num whitespace-nowrap", className)} style={style} title={formatExact(value)}>
      {formatQty(value)}
    </span>
  );
}

/* -- Score (risk, health) ------------------------------------------------- */
export function Score({ value, dp = 1, className, style }: { value: Numeric; dp?: number; className?: string; style?: React.CSSProperties }) {
  return (
    <span className={cn("num whitespace-nowrap", className)} style={style} title={formatExact(value)}>
      {formatScore(value, dp)}
    </span>
  );
}

/* -- Metric: the micro-label + figure pairing used throughout the product -- */
export function Metric({
  label, children, hint, tone, size = "md", align = "left", className,
}: {
  label: string;
  children: React.ReactNode;
  hint?: React.ReactNode;
  tone?: string;
  size?: "sm" | "md" | "lg" | "xl";
  align?: "left" | "right";
  className?: string;
}) {
  const figure = {
    sm: "text-base font-medium",
    md: "text-xl font-medium",
    lg: "text-2xl font-semibold",
    xl: "text-4xl font-semibold",
  }[size];
  return (
    <div className={cn("min-w-0", align === "right" && "text-right", className)}>
      <div className="micro truncate">{label}</div>
      <div className={cn("mt-0.5 font-ui tabular-nums", figure)} style={tone ? { color: tone } : undefined}>
        {children}
      </div>
      {hint ? <div className="mt-0.5 text-xs text-content-muted">{hint}</div> : null}
    </div>
  );
}

/* -- Delta: signed change with directional colour ------------------------- */
export function Delta({
  from, to, kind = "money", currency = "USD", className,
}: { from: Numeric; to: Numeric; kind?: "money" | "pct" | "score"; currency?: string; className?: string }) {
  const d = dec(to).minus(dec(from));
  const color = d.isZero() ? "var(--value-flat)" : d.isNegative() ? "var(--value-down)" : "var(--value-up)";
  const sign = d.isZero() ? "" : d.isNegative() ? "\u2212" : "+";
  const abs = d.abs();
  const text =
    kind === "money" ? `${currencySymbol(currency)}${formatAmount(abs.toString())}`
    : kind === "pct" ? `${formatAmount(abs.toString(), 2)} pp`
    : formatScore(abs.toString(), 2);
  return (
    <span className={cn("num whitespace-nowrap font-medium", className)} style={{ color }}>
      {sign}{text}
    </span>
  );
}
