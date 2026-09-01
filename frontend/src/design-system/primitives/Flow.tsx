/**
 * Progression and history: the approval stepper and the audit timeline.
 *
 * The stepper is the product's signature diagram — it answers "where is this,
 * and who is holding it" without reading a word.
 */
import { AlertTriangle, Check, Circle, Clock, RotateCcw, X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";
import { STEP_STATUS } from "@/design-system/semantics";
import type { ApprovalStepStatus } from "@/api/types";

export interface StepNode {
  id: string;
  label: string;
  sublabel?: string;
  status: ApprovalStepStatus | "ORIGIN" | "TERMINAL";
  detail?: React.ReactNode;
}

const ICON: Record<string, React.ReactNode> = {
  APPROVED: <Check className="size-3.5" strokeWidth={3} />,
  REJECTED: <X className="size-3.5" strokeWidth={3} />,
  REVISION_REQUESTED: <RotateCcw className="size-3" strokeWidth={2.5} />,
  SKIPPED: <Circle className="size-2.5" strokeWidth={3} />,
  STALE: <AlertTriangle className="size-3.5" strokeWidth={2.5} />,
  PENDING: <Clock className="size-3.5" strokeWidth={2.5} />,
  ORIGIN: <Check className="size-3.5" strokeWidth={3} />,
  TERMINAL: <Circle className="size-2.5" strokeWidth={3} />,
};

const nodeTone = (status: StepNode["status"], reached: boolean) => {
  if (status === "ORIGIN") return { fg: "var(--policy-passed)", bg: "var(--policy-passed)", ring: "transparent", text: "#fff" };
  if (status === "TERMINAL")
    return reached
      ? { fg: "var(--state-confirmed)", bg: "var(--state-confirmed)", ring: "transparent", text: "#fff" }
      : { fg: "var(--ink-400)", bg: "var(--ink-200)", ring: "transparent", text: "var(--ink-500)" };
  const t = STEP_STATUS[status];
  if (status === "PENDING") return { fg: t.fg, bg: "#fff", ring: t.fg, text: t.fg };
  return { fg: t.fg, bg: t.fg, ring: "transparent", text: "#fff" };
};

/**
 * Horizontal chain of approval stages. The active stage is ringed and slowly
 * pulses; everything decided is filled; everything ahead is inert grey.
 */
export function ApprovalFlow({ steps, className }: { steps: StepNode[]; className?: string }) {
  const activeIndex = steps.findIndex((s) => s.status === "PENDING");
  return (
    <ol className={cn("flex w-full items-start", className)} aria-label="Approval progression">
      {steps.map((step, i) => {
        const reached = activeIndex === -1 || i < activeIndex || step.status !== "TERMINAL";
        const tone = nodeTone(step.status, activeIndex === -1);
        const isActive = step.status === "PENDING";
        const nextDone = i < steps.length - 1 && (activeIndex === -1 || i < activeIndex);
        return (
          <li key={step.id} className="flex min-w-0 flex-1 items-start last:flex-none">
            <div className="flex min-w-0 flex-col items-center gap-1.5 px-1">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-base",
                  isActive && "animate-rail-pulse",
                )}
                style={{
                  background: tone.bg,
                  borderColor: tone.ring === "transparent" ? tone.bg : tone.ring,
                  color: tone.text,
                  boxShadow: isActive ? `0 0 0 4px ${tone.fg}1f` : undefined,
                }}
              >
                {ICON[step.status] ?? ICON.PENDING}
              </span>
              <div className="min-w-0 text-center">
                <div
                  className={cn("truncate font-ui text-xs font-semibold", !reached && "text-content-faint")}
                  style={reached ? { color: "var(--ink-800)" } : undefined}
                >
                  {step.label}
                </div>
                {step.sublabel ? (
                  <div className="truncate text-2xs uppercase tracking-wide text-content-faint">{step.sublabel}</div>
                ) : null}
                {step.detail ? <div className="mt-0.5 text-2xs text-content-muted">{step.detail}</div> : null}
              </div>
            </div>
            {i < steps.length - 1 ? (
              <span
                aria-hidden
                className="mt-3.5 h-[2px] min-w-4 flex-1 rounded-full transition-colors duration-slow"
                style={{ background: nextDone ? "var(--policy-passed)" : "var(--ink-200)" }}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/* -- Timeline: audit history --------------------------------------------- */
export interface TimelineEntry {
  id: string;
  title: React.ReactNode;
  actor?: React.ReactNode;
  at?: React.ReactNode;
  body?: React.ReactNode;
  tone?: string;
  icon?: React.ReactNode;
}

export function Timeline({ entries, className }: { entries: TimelineEntry[]; className?: string }) {
  return (
    <ol className={cn("relative space-y-0", className)}>
      {entries.map((e, i) => (
        <li key={e.id} className="relative flex gap-3 pb-4 last:pb-0">
          {i < entries.length - 1 ? (
            <span aria-hidden className="absolute left-[9px] top-5 bottom-0 w-px bg-line" />
          ) : null}
          <span
            className="relative z-10 mt-1 flex size-[19px] shrink-0 items-center justify-center rounded-full border-2 border-surface"
            style={{ background: e.tone ?? "var(--ink-300)" }}
          >
            {e.icon ? <span className="text-white">{e.icon}</span> : null}
          </span>
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-ui text-sm font-semibold text-content">{e.title}</span>
              {e.actor ? <span className="text-xs text-content-muted">{e.actor}</span> : null}
              {e.at ? <span className="ml-auto shrink-0 text-xs tabular-nums text-content-faint">{e.at}</span> : null}
            </div>
            {e.body ? <div className="mt-1 text-sm leading-[19px] text-content-secondary">{e.body}</div> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

/**
 * Horizontal proportional bar — used for warehouse allocation splits and for
 * one-time vs recurring billing. Communicates composition in one glance
 * without a two-slice donut.
 */
export function SplitBar({
  segments, height = 8, className, showLegend = true,
}: {
  segments: { id: string; label: string; value: number; color: string; caption?: string }[];
  height?: number;
  className?: string;
  showLegend?: boolean;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div className={className}>
      <div
        className="flex w-full overflow-hidden rounded-pill bg-ink-100"
        style={{ height }}
        role="img"
        aria-label={segments.map((s) => `${s.label}: ${s.value}`).join(", ")}
      >
        {segments.map((s) => (
          <span
            key={s.id}
            className="h-full transition-[width] duration-slow ease-smooth"
            style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
          />
        ))}
      </div>
      {showLegend ? (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {segments.map((s) => (
            <span key={s.id} className="inline-flex items-baseline gap-1.5 text-xs">
              <span aria-hidden className="size-2 shrink-0 translate-y-[1px] rounded-xs" style={{ background: s.color }} />
              <span className="text-content-secondary">{s.label}</span>
              <span className="num font-medium text-content">{s.caption ?? s.value}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Bullet gauge — a measured value against a threshold marker.
 * charts.csv "Performance vs Target" row. Used for blended risk vs the finance
 * escalation threshold, and for margin vs the policy floor.
 */
export function BulletGauge({
  value, max = 100, threshold, color, label, thresholdLabel, className,
}: {
  value: number; max?: number; threshold?: number; color: string;
  label?: React.ReactNode; thresholdLabel?: string; className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tPct = threshold !== undefined ? Math.max(0, Math.min(100, (threshold / max) * 100)) : undefined;
  return (
    <div className={className}>
      <div className="relative h-2 w-full overflow-hidden rounded-pill bg-ink-100">
        <span
          className="absolute inset-y-0 left-0 rounded-pill transition-[width] duration-slow ease-smooth"
          style={{ width: `${pct}%`, background: color }}
        />
        {tPct !== undefined ? (
          <span
            aria-hidden
            title={thresholdLabel}
            className="absolute inset-y-[-2px] w-[2px] rounded-full bg-ink-800"
            style={{ left: `${tPct}%` }}
          />
        ) : null}
      </div>
      {label ? <div className="mt-1 text-2xs text-content-faint">{label}</div> : null}
    </div>
  );
}
