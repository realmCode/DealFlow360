import * as React from "react";
import { cn } from "@/lib/cn";

/**
 * The panel is the only container in the product. There is no "card" with a
 * shadow and no nested rounding — borders carry the structure, which keeps a
 * dense screen legible instead of turning it into card soup.
 *
 * `rail` paints a 3px semantic bar down the leading edge. That is the signature
 * device: state is read from the rail before any text is parsed.
 */
export function Panel({
  rail, className, children, flush, ...props
}: React.HTMLAttributes<HTMLDivElement> & { rail?: string; flush?: boolean }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden border border-line bg-surface shadow-xs",
        flush ? "rounded-none border-x-0" : "rounded-lg",
        className,
      )}
      {...props}
    >
      {rail && (
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 w-[3px]"
          style={{ background: rail }}
        />
      )}
      {children}
    </div>
  );
}

export function PanelHead({
  title, subtitle, actions, icon, className, dense,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 border-b border-line",
        dense ? "min-h-[40px] px-3.5 py-2" : "min-h-[48px] px-4 py-2.5",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {icon ? <span className="shrink-0 text-content-muted">{icon}</span> : null}
        <div className="min-w-0">
          <h2 className="truncate font-ui text-[14px] font-semibold tracking-[-0.012em] text-content">{title}</h2>
          {subtitle ? (
            <p className="mt-0.5 truncate text-[12px] leading-[16px] text-content-muted">{subtitle}</p>
          ) : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
    </div>
  );
}

export function PanelBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />;
}

/**
 * Governance note — the amber-railed explanation strip.
 *
 * Reserved for one thing: the system explaining WHY it did something. Policy
 * reasons, routing rationale, allocation explanations, staleness causes. Never
 * used for generic info, so its presence always means "the engine is talking".
 */
export function GovNote({
  children, title, icon, className, tone = "governance",
}: {
  children: React.ReactNode;
  title?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
  tone?: "governance" | "critical" | "neutral";
}) {
  const palette = {
    governance: { rail: "var(--gov-500)", bg: "var(--gov-50)", fg: "var(--gov-700)" },
    critical: { rail: "var(--risk-critical)", bg: "var(--risk-critical-bg)", fg: "var(--risk-critical)" },
    neutral: { rail: "var(--ink-400)", bg: "var(--ink-50)", fg: "var(--ink-700)" },
  }[tone];
  return (
    <div
      className={cn("relative overflow-hidden rounded-md border py-2.5 pl-4 pr-3.5", className)}
      style={{ background: palette.bg, borderColor: `${palette.rail}2e` }}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: palette.rail }} />
      {title ? (
        <div className="mb-0.5 flex items-center gap-1.5 font-ui text-xs font-semibold" style={{ color: palette.fg }}>
          {icon}
          {title}
        </div>
      ) : null}
      <div className="text-[13px] leading-[19px]" style={{ color: "var(--ink-800)" }}>
        {children}
      </div>
    </div>
  );
}

/** A labelled definition row — used in every detail sidebar. */
export function Field({
  label, children, className,
}: { label: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3 py-1.5", className)}>
      <dt className="shrink-0 text-sm text-content-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right text-sm font-medium text-content">{children}</dd>
    </div>
  );
}

export function FieldList({ className, ...props }: React.HTMLAttributes<HTMLDListElement>) {
  return <dl className={cn("divide-y divide-line/70", className)} {...props} />;
}

/** Section heading inside a panel — smaller than PanelHead, no border. */
export function SectionLabel({
  children, actions, className,
}: { children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mb-2 flex items-center justify-between gap-2", className)}>
      <h3 className="micro">{children}</h3>
      {actions}
    </div>
  );
}
