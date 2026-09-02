import {
  Check, ChevronRight, Lightbulb, ScrollText, Send, ShieldQuestion, Sparkles, X,
} from "lucide-react";
import * as React from "react";
import { dec, formatAmount } from "@/api/money";
import type {
  PolicyEvaluationRead, QuoteVersionRead, RecommendationsRead, SimulationResult,
} from "@/api/types";
import {
  Button, GovNote, Money, Panel, PanelHead, Percent, POLICY, PolicyBadge, SectionLabel,
  Skeleton, toast, Tooltip,
} from "@/design-system";
import { MarginWaterfall } from "./MarginWaterfall";
import { RiskBreakdown } from "./RiskBreakdown";
import { cn } from "@/lib/cn";

/**
 * The decision intelligence column.
 *
 * It answers, in order: what is happening, why, what the commercial impact is,
 * which policy is affected, what approval is required, and what to do next.
 * Every answer is a field the backend returned — nothing here is derived
 * client-side.
 */
export function IntelligencePanel({
  version, evaluation, evaluationPending, recommendations, escalationThreshold,
  onSimulate, simulation, simulating, onClearSimulation, onAddRecommendation, onDismissRecommendation,
  editable,
}: {
  version: QuoteVersionRead;
  evaluation: PolicyEvaluationRead | undefined;
  evaluationPending: boolean;
  recommendations: RecommendationsRead | undefined;
  escalationThreshold?: string | null;
  onSimulate: (orderDiscountPct: string) => void;
  simulation: SimulationResult | null;
  simulating: boolean;
  onClearSimulation: () => void;
  onAddRecommendation: (productId: string, qty: string) => void;
  onDismissRecommendation: (productId: string) => void;
  editable: boolean;
}) {
  const [whatIf, setWhatIf] = React.useState("");

  const results = evaluation?.policy_results ?? [];
  const violations = results.filter((r) => r.status === "VIOLATED");
  const warnings = results.filter((r) => r.status === "WARNING");
  const passed = results.filter((r) => r.status === "PASSED" || r.status === "NOT_APPLICABLE");
  const required = (evaluation?.required_approvals ?? []) as { type: string; reason: string }[];
  const recs = recommendations?.recommendations ?? [];

  return (
    <div className="space-y-3">
      {/* -- WHAT IS HAPPENING -------------------------------------------- */}
      <Panel>
        <PanelHead
          dense
          icon={<ShieldQuestion className="size-4" />}
          title="Commercial position"
          subtitle="Computed by the backend on every change"
        />
        <div className="space-y-4 p-3.5">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="micro">Net revenue</div>
              <Money value={version.net_revenue} currency={version.currency} className="font-ui text-2xl font-semibold" />
            </div>
            <div className="text-right">
              <div className="micro">Margin</div>
              <div className="flex items-baseline justify-end gap-1.5">
                <Money value={version.margin} currency={version.currency} className="font-ui text-2xl font-semibold" />
              </div>
              <Percent value={version.margin_pct} className="text-sm font-medium text-content-muted" />
            </div>
          </div>

          <MarginWaterfall
            gross={version.gross_revenue}
            discount={version.total_discount}
            net={version.net_revenue}
            cost={version.total_cost}
            margin={version.margin}
            currency={version.currency}
          />

          <div className="grid grid-cols-2 gap-3 border-t border-line pt-3">
            <div>
              <div className="micro">One-time</div>
              <Money value={version.one_time_revenue} currency={version.currency} className="text-md font-medium" />
            </div>
            <div className="text-right">
              <div className="micro">Recurring</div>
              <Money value={version.recurring_revenue} currency={version.currency} className="text-md font-medium" />
            </div>
          </div>
        </div>
      </Panel>

      {/* -- RISK ---------------------------------------------------------- */}
      <Panel>
        <PanelHead dense icon={<Sparkles className="size-4" />} title="Blended risk" />
        <div className="p-3.5">
          {evaluationPending ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-40" />
              <Skeleton className="h-2 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : evaluation?.blended_risk ? (
            <RiskBreakdown risk={evaluation.blended_risk} escalationThreshold={escalationThreshold} />
          ) : (
            <p className="text-sm text-content-muted">
              Risk is scored once the version has at least one line.
            </p>
          )}
        </div>
      </Panel>

      {/* -- WHY / WHICH POLICY -------------------------------------------- */}
      <Panel rail={violations.length ? "var(--policy-violated)" : undefined}>
        <PanelHead
          dense
          icon={<ScrollText className="size-4" />}
          title="Policy evaluation"
          subtitle={
            evaluationPending
              ? undefined
              : `${violations.length} violated \u00b7 ${warnings.length} warning \u00b7 ${passed.length} clear`
          }
        />
        <div className="divide-y divide-line/70">
          {evaluationPending ? (
            <div className="space-y-2 p-3.5">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : results.length === 0 ? (
            <p className="p-3.5 text-sm text-content-muted">
              No policy has been evaluated yet. Add a line to run the engine.
            </p>
          ) : (
            [...violations, ...warnings, ...passed].map((r) => {
              const tone = POLICY[r.status];
              const dim = r.status === "PASSED" || r.status === "NOT_APPLICABLE";
              return (
                <div key={r.id} className={cn("px-3.5 py-2.5", dim && "opacity-70")}>
                  <div className="flex items-start gap-2">
                    <PolicyBadge value={r.status} size="sm" />
                    <span className="min-w-0 flex-1 font-ui text-xs font-semibold text-content">
                      {r.subject}
                    </span>
                    {dec(r.risk_contribution).greaterThan(0) ? (
                      <Tooltip content="Points this rule contributed to the blended risk score">
                        <span className="num shrink-0 rounded-sm px-1 text-2xs font-semibold" style={{ color: tone.fg, background: tone.bg }}>
                          +{dec(r.risk_contribution).toFixed(2)}
                        </span>
                      </Tooltip>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm leading-[18px] text-content-secondary">{r.reason}</p>
                  {r.status === "VIOLATED" ? (
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-2xs text-content-faint">
                      <span>
                        Actual <span className="num font-medium text-content-secondary">{formatAmount(r.actual_value, 2)}</span>
                      </span>
                      <span>
                        Limit <span className="num font-medium text-content-secondary">{formatAmount(r.threshold_value, 2)}</span>
                      </span>
                      <span>
                        Over by <span className="num font-medium text-[var(--policy-violated)]">{formatAmount(r.overage_points, 2)}</span>
                      </span>
                      {r.required_action ? (
                        <span className="rounded-sm bg-gov-100 px-1 font-semibold text-gov-700">
                          Needs {r.required_action.replace(/_/g, " ").toLowerCase()}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </Panel>

      {/* -- WHAT APPROVAL IS REQUIRED -------------------------------------- */}
      {required.length > 0 ? (
        <Panel rail="var(--gov-500)">
          <PanelHead dense icon={<Send className="size-4" />} title="Approval this will need" />
          <div className="space-y-2 p-3.5">
            {required.map((a) => (
              <GovNote key={a.type} title={a.type.replace(/_/g, " ")}>
                {a.reason}
              </GovNote>
            ))}
          </div>
        </Panel>
      ) : evaluation && !evaluation.requires_approval && results.length > 0 ? (
        <Panel rail="var(--policy-passed)">
          <div className="flex items-center gap-2 px-3.5 py-3">
            <Check className="size-4 text-[var(--policy-passed)]" />
            <p className="text-sm font-medium text-content">
              Inside policy — this version needs no approval.
            </p>
          </div>
        </Panel>
      ) : null}

      {/* -- WHAT SHOULD I DO: what-if -------------------------------------- */}
      {editable ? (
        <Panel>
          <PanelHead
            dense
            icon={<Lightbulb className="size-4" />}
            title="What if"
            subtitle="Scores a hypothetical without saving anything"
          />
          <div className="space-y-3 p-3.5">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <label htmlFor="whatif" className="micro mb-1 block">Order discount</label>
                <div className="relative">
                  <input
                    id="whatif"
                    inputMode="decimal"
                    value={whatIf}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === "" || /^\d*\.?\d*$/.test(v)) setWhatIf(v);
                    }}
                    placeholder="0"
                    className="num h-8 w-full rounded-md border border-line-strong bg-white pl-2.5 pr-7 text-right text-base focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/25"
                  />
                  <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-content-faint">%</span>
                </div>
              </div>
              <Button
                size="md"
                loading={simulating}
                disabled={whatIf === ""}
                onClick={() => onSimulate(whatIf)}
              >
                Score it
              </Button>
            </div>

            {simulation ? (
              <div className="rounded-md border border-line bg-surface-sunken p-3">
                <div className="mb-2 flex items-center justify-between">
                  <SectionLabel className="mb-0">Simulated, not saved</SectionLabel>
                  <button
                    type="button"
                    onClick={onClearSimulation}
                    className="cursor-pointer rounded-sm p-0.5 text-content-faint hover:bg-ink-100 hover:text-content"
                    aria-label="Clear simulation"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
                <p className="text-sm leading-[19px] text-content-secondary">{simulation.verdict}</p>
                <dl className="mt-2 grid grid-cols-3 gap-2 border-t border-line pt-2">
                  <div>
                    <dt className="micro">Margin</dt>
                    <dd>
                      <Money
                        value={simulation.margin_delta} signed
                        className="text-sm font-semibold"
                        style={{ color: dec(simulation.margin_delta).isNegative() ? "var(--value-down)" : "var(--value-up)" }}
                      />
                    </dd>
                  </div>
                  <div>
                    <dt className="micro">Revenue</dt>
                    <dd>
                      <Money
                        value={simulation.revenue_delta} signed
                        className="text-sm font-semibold"
                        style={{ color: dec(simulation.revenue_delta).isNegative() ? "var(--value-down)" : "var(--value-up)" }}
                      />
                    </dd>
                  </div>
                  <div>
                    <dt className="micro">Risk</dt>
                    <dd>
                      <span
                        className="num text-sm font-semibold"
                        style={{ color: dec(simulation.risk_delta).isNegative() ? "var(--value-up)" : "var(--value-down)" }}
                      >
                        {dec(simulation.risk_delta).isNegative() ? "\u2212" : "+"}
                        {dec(simulation.risk_delta).abs().toFixed(2)}
                      </span>
                    </dd>
                  </div>
                </dl>
                {simulation.approvals_added?.length ? (
                  <p className="mt-2 text-xs text-[var(--policy-violated)]">
                    Would add approval from {simulation.approvals_added.join(", ")}
                  </p>
                ) : null}
                {simulation.approvals_removed?.length ? (
                  <p className="mt-2 text-xs text-[var(--policy-passed)]">
                    Would remove approval from {simulation.approvals_removed.join(", ")}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </Panel>
      ) : null}

      {/* -- WHAT SHOULD I DO: recommendations ------------------------------ */}
      {recs.length > 0 ? (
        <Panel>
          <PanelHead
            dense
            icon={<Sparkles className="size-4" />}
            title="Attach opportunities"
            subtitle="Computed from this configuration"
          />
          <div className="divide-y divide-line/70">
            {recs.map((r) => (
              <div key={r.product_id} className="px-3.5 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-ui text-sm font-semibold text-content">{r.product_name}</p>
                    <p className="text-2xs uppercase tracking-wide text-content-faint">
                      {r.kind.replace(/_/g, " ")} &middot; {r.confidence} confidence
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <Money value={r.estimated_revenue} className="text-sm font-semibold" />
                    <div className="text-2xs text-content-muted">
                      <Percent value={r.estimated_margin_pct} dp={1} /> margin
                    </div>
                  </div>
                </div>
                <p className="mt-1.5 text-sm leading-[18px] text-content-secondary">{r.reason}</p>
                <p className="mt-1 text-xs text-content-muted">{r.impact}</p>
                {editable ? (
                  <div className="mt-2 flex items-center gap-1.5">
                    <Button
                      size="xs" variant="secondary"
                      icon={<ChevronRight className="size-3" />}
                      onClick={() => {
                        onAddRecommendation(r.product_id, r.suggested_quantity);
                        toast.success("Line added", r.product_name);
                      }}
                    >
                      Add {r.suggested_quantity} to quote
                    </Button>
                    <Button size="xs" variant="ghost" onClick={() => onDismissRecommendation(r.product_id)}>
                      Dismiss
                    </Button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
