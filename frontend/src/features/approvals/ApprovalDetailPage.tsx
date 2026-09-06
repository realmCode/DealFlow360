import { AlertTriangle, ArrowLeft, ArrowRight, Check, RotateCcw, X } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { formatDateTime, formatRelative } from "@/api/money";
import { useApproval, useApprovalDecision, useDeal, usePolicyResults, useQuote, useVersion } from "@/api/queries";
import type { ApprovalStepRead } from "@/api/types";
import { useAuth, useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  ApprovalFlow, ApprovalStatusBadge, Button, Dialog, ErrorState, Field, FieldList, GovNote,
  Money, Panel, PanelHead, Percent, POLICY, PolicyBadge, SectionLabel, Score,
  Skeleton, type StepNode, Textarea, TierBadge, Timeline, toast, VersionStatusBadge,
} from "@/design-system";
import { RiskBreakdown } from "@/features/builder/RiskBreakdown";
import { dec } from "@/api/money";

const ROLE_FOR_LEVEL: Record<string, string> = {
  SALES_MANAGER: "MANAGER",
  FINANCE: "FINANCE",
  EXECUTIVE: "ADMIN",
};

export function ApprovalDetailPage() {
  const { requestId } = useParams<{ requestId: string }>();
  const { user } = useAuth();
  const can = useCan();

  const approval = useApproval(requestId);
  const req = approval.data;
  const version = useVersion(req?.quote_version_id);
  const quote = useQuote(req?.quote_id);
  const deal = useDeal(quote.data?.deal_id);
  const evaluation = usePolicyResults(req?.quote_version_id);
  const decide = useApprovalDecision(requestId!);

  const [action, setAction] = React.useState<"approve" | "reject" | "request-revision" | null>(null);
  const [reason, setReason] = React.useState("");

  if (approval.isPending) {
    return (
      <Page title={<Skeleton className="h-7 w-64" />}>
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="mt-3 h-72 w-full rounded-lg" />
      </Page>
    );
  }
  if (approval.isError) {
    return (
      <Page title="Approval">
        <Panel><ErrorState error={approval.error} onRetry={approval.refetch} /></Panel>
      </Page>
    );
  }

  const r = req!;
  const v = version.data;
  const steps = r.steps ?? [];
  const currentStep = steps.find((s: ApprovalStepRead) => s.status === "PENDING");
  const isMyStep =
    Boolean(currentStep) &&
    (user?.role === "ADMIN" || user?.role === ROLE_FOR_LEVEL[currentStep!.level]);
  const isAuthor = r.requested_by_user_id === user?.id;
  const canDecide = can.approve && isMyStep && !isAuthor && r.status === "PENDING";
  const isStale = r.status === "STALE" || Boolean(v?.is_stale);

  const flow: StepNode[] = [
    {
      id: "submitted",
      label: "Submitted",
      sublabel: r.requested_by_email?.split("@")[0],
      status: "ORIGIN",
      detail: formatRelative(r.created_at),
    },
    ...steps.map((s: ApprovalStepRead) => ({
      id: s.id,
      label: s.level.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      sublabel: s.required_role,
      status: s.status,
      detail: s.decided_by_email ? s.decided_by_email.split("@")[0] : undefined,
    })),
    {
      id: "confirmed",
      label: "Confirmation",
      sublabel: "customer",
      status: "TERMINAL" as const,
      detail: v?.status === "CONFIRMED" ? "done" : undefined,
    },
  ];

  const submit = () => {
    if (!action) return;
    decide.mutate(
      { action, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success(
            action === "approve" ? "Approved" : action === "reject" ? "Rejected" : "Sent back for revision",
            `${r.quote_number} v${r.version_number}`,
          );
          setAction(null);
          setReason("");
        },
        onError: toast.fromError,
      },
    );
  };

  // `financials` is an open object in the spec; read it defensively.
  const fin = (k: string): string | undefined => {
    const raw = (r.financials as Record<string, unknown> | undefined)?.[k];
    return typeof raw === "string" ? raw : undefined;
  };
  const results = evaluation.data?.policy_results ?? [];
  const violated = results.filter((x) => x.status === "VIOLATED");

  return (
    <Page
      title={
        <span className="flex flex-wrap items-center gap-2.5">
          <span className="num">{r.quote_number}</span>
          <span className="text-content-muted">v{r.version_number}</span>
          <ApprovalStatusBadge value={r.status} />
          {isStale ? (
            <span className="inline-flex items-center gap-1 rounded-sm bg-[var(--risk-critical-bg)] px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wide text-[var(--risk-critical)]">
              <AlertTriangle className="size-3" /> Stale
            </span>
          ) : null}
        </span>
      }
      subtitle={
        <Link to={`/approvals`} className="inline-flex items-center gap-1 hover:text-content">
          <ArrowLeft className="size-3.5" /> Approval inbox
        </Link>
      }
      actions={
        canDecide ? (
          <>
            <Button variant="approve" icon={<Check className="size-3.5" />} onClick={() => setAction("approve")}>
              Approve
            </Button>
            <Button variant="governance" icon={<RotateCcw className="size-3.5" />} onClick={() => setAction("request-revision")}>
              Return for revision
            </Button>
            <Button variant="danger" icon={<X className="size-3.5" />} onClick={() => setAction("reject")}>
              Reject
            </Button>
          </>
        ) : (
          <Button variant="secondary" asChild icon={<ArrowRight className="size-3.5" />}>
            <Link to={`/quotes/${r.quote_id}`}>Open quotation</Link>
          </Button>
        )
      }
    >
      {/* -- why you cannot act ---------------------------------------------- */}
      {!canDecide && r.status === "PENDING" ? (
        <GovNote className="mb-3" tone={isAuthor ? "critical" : "neutral"} title="You are viewing this read-only">
          {isAuthor
            ? "You submitted this quotation. Separation of duties means it must be approved by someone else."
            : !can.approve
              ? "Your role does not include approval authority."
              : `This step needs ${currentStep?.required_role ?? "another approver"}.`}
        </GovNote>
      ) : null}

      {isStale ? (
        <Panel rail="var(--risk-critical)" className="mb-3 bg-[var(--risk-critical-bg)]/30">
          <div className="flex flex-wrap items-center gap-3 p-4">
            <AlertTriangle className="size-5 shrink-0 text-[var(--risk-critical)]" />
            <div className="min-w-0 flex-1">
              <p className="font-ui text-md font-semibold text-content">
                A material change invalidated the earlier approval
              </p>
              <p className="mt-0.5 text-sm text-content-secondary">
                {r.stale_reason ?? "The terms moved after this quotation was approved, so it must be decided again."}
              </p>
            </div>
            <Button variant="secondary" asChild icon={<ArrowRight className="size-3.5" />}>
              <Link to={`/quotes/${r.quote_id}/versions/${r.quote_version_id}/impact`}>Review the diff</Link>
            </Button>
          </div>
        </Panel>
      ) : null}

      {/* -- the progression -------------------------------------------------- */}
      <Panel className="mb-3">
        <PanelHead title="Approval progression" subtitle="Where this decision sits, and who holds it" />
        <div className="px-6 py-5">
          <ApprovalFlow steps={flow} />
        </div>
      </Panel>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-3">
          {/* -- the numbers under review ----------------------------------- */}
          <Panel>
            <PanelHead title="The numbers under review" />
            <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 lg:grid-cols-5">
              {[
                { label: "Value", node: <Money value={fin("total_revenue") ?? v?.net_revenue ?? "0"} /> },
                { label: "Discount", node: <Percent value={fin("effective_discount_pct") ?? v?.effective_discount_pct ?? "0"} dp={2} /> },
                { label: "Margin", node: <Money value={fin("margin") ?? v?.margin ?? "0"} /> },
                { label: "Margin %", node: <Percent value={fin("margin_pct") ?? v?.margin_pct ?? "0"} /> },
                { label: "Blended risk", node: <Score value={r.blended_risk_score} dp={2} /> },
              ].map((c) => (
                <div key={c.label} className="bg-surface px-3 py-2.5">
                  <div className="micro">{c.label}</div>
                  <div className="mt-0.5 font-ui text-md font-semibold text-content">{c.node}</div>
                </div>
              ))}
            </div>
          </Panel>

          {/* -- why this was flagged ---------------------------------------- */}
          <Panel rail={violated.length ? "var(--policy-violated)" : undefined}>
            <PanelHead
              title="Why this quotation was flagged"
              subtitle={`${violated.length} of ${results.length} rules breached`}
            />
            {evaluation.isPending ? (
              <div className="p-4"><Skeleton className="h-24 w-full" /></div>
            ) : results.length === 0 ? (
              <p className="px-4 py-6 text-sm text-content-muted">No policy results recorded for this version.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-line bg-surface-sunken">
                      {["Rule", "Subject", "Actual", "Limit", "Over by", "Risk", "Status"].map((h, i) => (
                        <th key={h} className={`h-8 px-3 font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint ${i > 1 ? "text-right" : ""}`}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...violated, ...results.filter((x) => x.status !== "VIOLATED")].map((p) => (
                      <tr key={p.id} className="border-b border-line/60 align-top">
                        <td className="px-3 py-2 text-xs uppercase tracking-wide text-content-muted">
                          {p.rule.replace(/_/g, " ")}
                        </td>
                        <td className="px-3 py-2">
                          <div className="font-medium text-content">{p.subject}</div>
                          <div className="mt-0.5 max-w-md text-xs leading-[17px] text-content-secondary">{p.reason}</div>
                        </td>
                        <td className="px-3 py-2 text-right"><span className="num">{dec(p.actual_value).toFixed(2)}</span></td>
                        <td className="px-3 py-2 text-right"><span className="num text-content-muted">{dec(p.threshold_value).toFixed(2)}</span></td>
                        <td className="px-3 py-2 text-right">
                          {dec(p.overage_points).greaterThan(0) ? (
                            <span className="num font-semibold text-[var(--policy-violated)]">
                              {dec(p.overage_points).toFixed(2)}
                            </span>
                          ) : (
                            <span className="text-content-faint">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {dec(p.risk_contribution).greaterThan(0) ? (
                            <span className="num" style={{ color: POLICY[p.status].fg }}>
                              +{dec(p.risk_contribution).toFixed(2)}
                            </span>
                          ) : (
                            <span className="text-content-faint">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right"><PolicyBadge value={p.status} size="sm" /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="border-t border-line p-3.5">
              <GovNote title="How the routing was decided">{r.reason}</GovNote>
            </div>
          </Panel>

          {/* -- decision history -------------------------------------------- */}
          <Panel>
            <PanelHead title="Decision history" />
            <div className="p-4">
              {(r.decisions?.length ?? 0) === 0 ? (
                <p className="text-sm text-content-muted">No decisions recorded yet.</p>
              ) : (
                <Timeline
                  entries={r.decisions!.map((d) => ({
                    id: d.id,
                    title:
                      d.decision === "APPROVE" ? "Approved"
                      : d.decision === "REJECT" ? "Rejected"
                      : "Returned for revision",
                    actor: d.actor_email,
                    at: formatDateTime(d.decided_at),
                    body: d.reason,
                    tone:
                      d.decision === "APPROVE" ? "var(--policy-passed)"
                      : d.decision === "REJECT" ? "var(--policy-violated)"
                      : "var(--gov-500)",
                  }))}
                />
              )}
            </div>
          </Panel>
        </div>

        {/* -- rail ------------------------------------------------------------ */}
        <div className="min-w-0 space-y-3">
          <Panel>
            <PanelHead dense title="Context" />
            <div className="px-3.5 py-1">
              <FieldList>
                <Field label="Customer">
                  <span className="flex items-center justify-end gap-2">
                    {r.customer_name}
                    {deal.data?.customer_tier ? <TierBadge tier={deal.data.customer_tier} /> : null}
                  </span>
                </Field>
                <Field label="Quotation">
                  <Link to={`/quotes/${r.quote_id}`} className="text-accent-600 hover:underline">
                    {r.quote_number}
                  </Link>
                </Field>
                <Field label="Version">
                  <span className="flex items-center justify-end gap-2">
                    v{r.version_number}
                    {v ? <VersionStatusBadge value={v.status} size="sm" /> : null}
                  </span>
                </Field>
                <Field label="Requested by">{r.requested_by_email}</Field>
                <Field label="Submitted">{formatDateTime(r.created_at)}</Field>
                {r.decided_at ? <Field label="Decided">{formatDateTime(r.decided_at)}</Field> : null}
                <Field label="Current step">{r.current_step_sequence}</Field>
              </FieldList>
            </div>
          </Panel>

          {evaluation.data?.blended_risk ? (
            <Panel>
              <PanelHead dense title="Risk decomposition" />
              <div className="p-3.5">
                <RiskBreakdown risk={evaluation.data.blended_risk} />
              </div>
            </Panel>
          ) : null}

          {canDecide ? (
            <Panel rail="var(--accent-500)">
              <div className="p-3.5">
                <SectionLabel>Your decision</SectionLabel>
                <p className="text-sm leading-[19px] text-content-secondary">
                  You are deciding step {currentStep!.sequence} of {steps.length} as{" "}
                  <span className="font-medium text-content">{currentStep!.level.replace(/_/g, " ")}</span>.
                  A reason is required and is written to the audit trail.
                </p>
                <div className="mt-3 grid grid-cols-1 gap-1.5">
                  <Button variant="approve" icon={<Check className="size-3.5" />} onClick={() => setAction("approve")}>
                    Approve
                  </Button>
                  <div className="grid grid-cols-2 gap-1.5">
                    <Button variant="governance" size="sm" onClick={() => setAction("request-revision")}>
                      Return
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => setAction("reject")}>
                      Reject
                    </Button>
                  </div>
                </div>
              </div>
            </Panel>
          ) : null}
        </div>
      </div>

      {/* -- decision dialog --------------------------------------------------- */}
      <Dialog
        open={action !== null}
        onOpenChange={(v2) => !v2 && setAction(null)}
        title={
          action === "approve" ? "Approve this quotation"
          : action === "reject" ? "Reject this quotation"
          : "Return for revision"
        }
        description={
          action === "approve"
            ? steps.length > 1 && currentStep?.sequence !== steps.length
              ? "This clears your step. The next approver is notified."
              : "This is the final step — the version becomes APPROVED."
            : action === "reject"
              ? "The version becomes immutable and the quotation cannot proceed."
              : "The version returns to DRAFT so the author can change it."
        }
        width="md"
        footer={
          <>
            <Button onClick={() => setAction(null)} disabled={decide.isPending}>Cancel</Button>
            <Button
              variant={action === "approve" ? "approve" : action === "reject" ? "danger" : "governance"}
              loading={decide.isPending}
              disabled={!reason.trim()}
              onClick={submit}
            >
              {action === "approve" ? "Approve" : action === "reject" ? "Reject" : "Return for revision"}
            </Button>
          </>
        }
      >
        <SectionLabel>Reason (recorded in the audit trail)</SectionLabel>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={
            action === "approve"
              ? "e.g. Strategic account, margin still clears the floor"
              : "e.g. Discount on hardware exceeds what this tier supports"
          }
          aria-label="Reason for your decision"
          autoFocus
        />
        {action === "approve" && isStale ? (
          <GovNote className="mt-3" tone="critical" title="This is a re-approval">
            The earlier approval was invalidated by a material change. Approving now unblocks the customer&rsquo;s
            confirmation.
          </GovNote>
        ) : null}
      </Dialog>
    </Page>
  );
}
