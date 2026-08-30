import * as React from "react";
import { cn } from "@/lib/cn";
import type { Tone } from "@/design-system/semantics";
import {
  APPROVAL_STATUS, DEAL_STAGE, INVOICE_STATUS, ORDER_STATUS, POLICY,
  RISK, SEVERITY, STEP_STATUS, VERSION_STATUS,
} from "@/design-system/semantics";
import type {
  ApprovalRequestStatus, ApprovalStepStatus, DealStage, InvoiceStatus,
  PolicyResultStatus, QuoteVersionStatus, RiskBand, SalesOrderStatus, Severity,
} from "@/api/types";

/**
 * A badge always pairs colour with a word. Colour is never the only carrier of
 * meaning (ux-guidelines.csv, severity High).
 */
export function Badge({
  tone, children, dot = true, size = "md", variant = "tint", className,
}: {
  tone?: Tone;
  children?: React.ReactNode;
  dot?: boolean;
  size?: "sm" | "md";
  variant?: "tint" | "outline" | "solid";
  className?: string;
}) {
  const fg = tone?.fg ?? "var(--ink-600)";
  const bg = tone?.bg ?? "var(--ink-100)";
  const style: React.CSSProperties =
    variant === "solid"
      ? { background: fg, color: "#fff", borderColor: fg }
      : variant === "outline"
        ? { color: fg, borderColor: fg, background: "transparent" }
        : { color: fg, background: bg, borderColor: "transparent" };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border font-ui font-medium whitespace-nowrap",
        size === "sm" ? "h-5 px-1.5 text-2xs tracking-wide" : "h-6 px-2 text-xs",
        className,
      )}
      style={style}
    >
      {dot && variant !== "solid" && (
        <span aria-hidden className="size-1.5 shrink-0 rounded-full" style={{ background: fg }} />
      )}
      {children ?? tone?.label}
    </span>
  );
}

const make = <K extends string>(map: Record<K, Tone>) =>
  function StatusBadge({ value, ...rest }: { value: K } & Omit<React.ComponentProps<typeof Badge>, "tone" | "children">) {
    return <Badge tone={map[value]} {...rest} />;
  };

export const RiskBadge = make<RiskBand>(RISK);
export const PolicyBadge = make<PolicyResultStatus>(POLICY);
export const SeverityBadge = make<Severity>(SEVERITY);
export const VersionStatusBadge = make<QuoteVersionStatus>(VERSION_STATUS);
export const ApprovalStatusBadge = make<ApprovalRequestStatus>(APPROVAL_STATUS);
export const StepStatusBadge = make<ApprovalStepStatus>(STEP_STATUS);
export const OrderStatusBadge = make<SalesOrderStatus>(ORDER_STATUS);
export const InvoiceStatusBadge = make<InvoiceStatus>(INVOICE_STATUS);
export const DealStageBadge = make<DealStage>(DEAL_STAGE);

/** Tier chip — customer tier drives every discount ceiling, so it earns a slot. */
export function TierBadge({ tier }: { tier: string }) {
  const palette: Record<string, string> = {
    BRONZE: "#9a6b3f", SILVER: "#7b8794", GOLD: "#b7791f", PLATINUM: "#4c5c9c",
  };
  const fg = palette[tier] ?? "var(--ink-600)";
  return (
    <span
      className="inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 font-ui text-xs font-semibold tracking-wide"
      style={{ color: fg, borderColor: `${fg}40`, background: `${fg}12` }}
    >
      <span aria-hidden className="size-1.5 rounded-full" style={{ background: fg }} />
      {tier.charAt(0) + tier.slice(1).toLowerCase()}
    </span>
  );
}
