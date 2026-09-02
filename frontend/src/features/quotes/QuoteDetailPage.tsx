import {
  AlertTriangle, ArrowRight, GitBranch, History, MessageSquare, Pencil, Send, XCircle,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { formatDateTime, formatRelative } from "@/api/money";
import { errorTitle } from "@/api/errors";
import {
  useDeal, useImpact, useLoseQuote, useNegotiation, usePolicyResults, useQuote,
  useQuoteTimeline, useSellerReply, useVersion, useVersionApproval, useVersionMutations,
} from "@/api/queries";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  ApprovalStatusBadge, Async, Button, Dialog, ErrorState, Field, FieldList, GovNote,
  Money, Panel, PanelHead, Percent, Qty, RiskBadge, SectionLabel, Skeleton, Textarea, TierBadge,
  Timeline, toast, VERSION_STATUS, VersionStatusBadge,
} from "@/design-system";
import { EVENT_TONE } from "@/features/intelligence/eventTone";
import { cn } from "@/lib/cn";

export function QuoteDetailPage() {
  const { quoteId } = useParams<{ quoteId: string }>();
  const nav = useNavigate();
  const can = useCan();

  const quote = useQuote(quoteId);
  // QuoteRead has no customer fields — they live on the deal.
  const deal = useDeal(quote.data?.deal_id);
  const versionId = quote.data?.current_version_id;
  const version = useVersion(versionId ?? undefined);
  const evaluation = usePolicyResults(versionId);
  const approval = useVersionApproval(versionId);
  const impact = useImpact(versionId);
  const timeline = useQuoteTimeline(quoteId);
  const negotiation = useNegotiation(quoteId);
  const m = useVersionMutations(versionId ?? "", quoteId);
  const lose = useLoseQuote(quoteId!);
  const reply = useSellerReply(quoteId!);

  const [revising, setRevising] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [losing, setLosing] = React.useState(false);
  const [replyText, setReplyText] = React.useState("");

  if (quote.isPending) {
    return (
      <Page title={<Skeleton className="h-7 w-56" />}>
        <Skeleton className="h-72 w-full rounded-lg" />
      </Page>
    );
  }
  if (quote.isError) {
    return (
      <Page title="Quotation">
        <Panel><ErrorState error={quote.error} onRetry={quote.refetch} /></Panel>
      </Page>
    );
  }

  const q = quote.data!;
  const v = version.data;
  const isStale = Boolean(v?.is_stale) || Boolean(impact.data?.blocks_confirmation);
  const versions = [...(q.versions ?? [])].sort((a, b) => b.version_number - a.version_number);

  return (
    <Page
      title={
        <span className="flex flex-wrap items-center gap-2.5">
          <span className="num">{q.quote_number}</span>
          <span className="text-content-muted">/</span>
          <span>{q.title}</span>
        </span>
      }
      subtitle={
        <span className="flex flex-wrap items-center gap-2">
          <span>{deal.data?.customer_display_name ?? "\u2014"}</span>
          {deal.data?.customer_tier ? <TierBadge tier={deal.data.customer_tier} /> : null}
          {v ? <VersionStatusBadge value={v.status} /> : null}
          <span className="text-content-faint">Version {v?.version_number ?? "\u2014"}</span>
        </span>
      }
      actions={
        <>
          {v?.is_editable && can.authorQuotes ? (
            <Button variant="primary" icon={<Pencil className="size-3.5" />} asChild>
              <Link to={`/quotes/${quoteId}/versions/${v.id}/build`}>Edit in builder</Link>
            </Button>
          ) : null}
          {v && !v.is_editable && can.authorQuotes && !["CONFIRMED", "REJECTED", "SUPERSEDED"].includes(v.status) ? (
            <Button icon={<GitBranch className="size-3.5" />} onClick={() => setRevising(true)}>
              Create revision
            </Button>
          ) : null}
          {v?.status === "APPROVED" && can.authorQuotes ? (
            <Button
              variant="primary" icon={<Send className="size-3.5" />}
              loading={m.send.isPending}
              onClick={() =>
                m.send.mutate(undefined, {
                  onSuccess: () => toast.success("Sent to the customer portal"),
                  onError: toast.fromError,
                })
              }
            >
              Send to customer
            </Button>
          ) : null}
          {can.authorQuotes && q.status === "OPEN" ? (
            <Button variant="ghost" icon={<XCircle className="size-3.5" />} onClick={() => setLosing(true)}>
              Mark lost
            </Button>
          ) : null}
        </>
      }
    >
      {/* -- the stale banner is the loudest thing on the page -------------- */}
      {isStale ? (
        <Panel rail="var(--risk-critical)" className="mb-3 bg-[var(--risk-critical-bg)]/40">
          <div className="flex flex-wrap items-center gap-3 px-4 py-3">
            <AlertTriangle aria-hidden className="size-5 shrink-0 text-[var(--risk-critical)]" />
            <div className="min-w-0 flex-1">
              <p className="font-ui text-md font-semibold text-content">
                This quotation changed after approval
              </p>
              <p className="mt-0.5 text-sm text-content-secondary">
                The previous approval is no longer valid, and confirmation is blocked until this version is
                approved again.
              </p>
            </div>
            <Button variant="danger" icon={<ArrowRight className="size-3.5" />} asChild>
              <Link to={`/quotes/${quoteId}/versions/${versionId}/impact`}>Review what changed</Link>
            </Button>
          </div>
        </Panel>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-3">
          {/* -- commercial summary ---------------------------------------- */}
          <Panel>
            <PanelHead title="Commercial summary" subtitle="Authoritative values from the last calculation" />
            {version.isPending ? (
              <div className="p-4"><Skeleton className="h-20 w-full" /></div>
            ) : v ? (
              <>
                <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    { label: "Gross", node: <Money value={v.gross_revenue} currency={v.currency} /> },
                    { label: "Discount", node: <Money value={v.total_discount} currency={v.currency} /> },
                    { label: "Net revenue", node: <Money value={v.net_revenue} currency={v.currency} /> },
                    { label: "Cost", node: <Money value={v.total_cost} currency={v.currency} /> },
                    { label: "Margin", node: <Money value={v.margin} currency={v.currency} /> },
                    { label: "Margin %", node: <Percent value={v.margin_pct} /> },
                  ].map((cell) => (
                    <div key={cell.label} className="bg-surface px-3 py-2.5">
                      <div className="micro">{cell.label}</div>
                      <div className="mt-0.5 font-ui text-md font-semibold text-content">{cell.node}</div>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line px-4 py-2.5">
                  {v.risk_band ? (
                    <span className="flex items-center gap-2">
                      <span className="micro">Blended risk</span>
                      <span className="num text-sm font-semibold">{Number(v.blended_risk_score ?? 0).toFixed(2)}</span>
                      <RiskBadge value={v.risk_band} size="sm" />
                    </span>
                  ) : null}
                  <span className="flex items-center gap-2">
                    <span className="micro">One-time</span>
                    <Money value={v.one_time_revenue} currency={v.currency} className="text-sm" />
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="micro">Recurring</span>
                    <Money value={v.recurring_revenue} currency={v.currency} className="text-sm" />
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="micro">Terms</span>
                    <span className="text-sm">{v.payment_terms?.replace(/_/g, " ")}</span>
                  </span>
                </div>
              </>
            ) : null}
          </Panel>

          {/* -- lines ------------------------------------------------------ */}
          <Panel>
            <PanelHead title="Line items" subtitle={v ? `${(v.lines ?? []).length} lines` : undefined} />
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-line bg-surface-sunken">
                    {["Product", "Qty", "Unit", "Disc.", "Amount", "Margin"].map((h, i) => (
                      <th key={h} className={cn(
                        "h-8 px-3 font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint",
                        i > 0 && "text-right",
                      )}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {((v?.lines ?? [])).map((l) => (
                    <tr key={l.id} className="border-b border-line/60">
                      <td className="px-3 py-2">
                        <div className="font-medium text-content">{l.description}</div>
                        <div className="text-2xs uppercase tracking-wide text-content-faint">{l.category}</div>
                      </td>
                      <td className="px-3 py-2 text-right"><Qty value={l.quantity} /></td>
                      <td className="px-3 py-2 text-right"><Money value={l.unit_net_price} currency={v?.currency ?? "USD"} /></td>
                      <td className="px-3 py-2 text-right"><Percent value={l.discount_pct} dp={1} /></td>
                      <td className="px-3 py-2 text-right"><Money value={l.net_amount} currency={v?.currency ?? "USD"} className="font-semibold" /></td>
                      <td className="px-3 py-2 text-right"><Percent value={l.line_margin_pct} dp={1} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* -- negotiation ------------------------------------------------ */}
          <Panel>
            <PanelHead
              icon={<MessageSquare className="size-4" />}
              title="Negotiation"
              subtitle={negotiation.data ? `Thread is ${negotiation.data.status?.replace(/_/g, " ").toLowerCase()}` : undefined}
            />
            {negotiation.isPending ? (
              <div className="p-4"><Skeleton className="h-16 w-full" /></div>
            ) : (negotiation.data?.messages?.length ?? 0) === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-content-muted">
                No messages yet. The thread opens when the quotation is sent to the customer.
              </p>
            ) : (
              <ul className="divide-y divide-line/70">
                {(negotiation.data?.messages ?? []).map((msg) => (
                  <li key={msg.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className={cn(
                        "rounded-sm px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wide",
                        msg.author_kind === "CUSTOMER"
                          ? "bg-[var(--state-negotiating-bg)] text-[var(--state-negotiating)]"
                          : msg.author_kind === "SYSTEM"
                            ? "bg-ink-100 text-content-muted"
                            : "bg-accent-100 text-accent-700",
                      )}>
                        {msg.author_kind}
                      </span>
                      <span className="text-xs text-content-muted">{msg.message_type?.replace(/_/g, " ").toLowerCase()}</span>
                      <span className="ml-auto text-xs text-content-faint">{formatRelative(msg.created_at)}</span>
                    </div>
                    <p className="mt-1 text-sm leading-[19px] text-content">{msg.body}</p>
                  </li>
                ))}
              </ul>
            )}
            {negotiation.data && can.authorQuotes ? (
              <div className="border-t border-line p-3">
                <Textarea
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Reply to the customer\u2026"
                  aria-label="Reply to the customer"
                />
                <div className="mt-2 flex justify-end">
                  <Button
                    size="sm" variant="primary" disabled={!replyText.trim()} loading={reply.isPending}
                    onClick={() =>
                      reply.mutate({ body: replyText.trim() }, {
                        onSuccess: () => { setReplyText(""); toast.success("Reply sent"); },
                        onError: toast.fromError,
                      })
                    }
                  >
                    Send reply
                  </Button>
                </div>
              </div>
            ) : null}
          </Panel>
        </div>

        {/* -- side rail ------------------------------------------------------ */}
        <div className="min-w-0 space-y-3">
          <Panel>
            <PanelHead dense title="Approval" />
            <div className="p-3.5">
              {approval.isPending ? (
                <Skeleton className="h-12 w-full" />
              ) : approval.data?.approval_request ? (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <ApprovalStatusBadge value={approval.data.approval_request.status} />
                    <Button size="xs" variant="ghost" asChild>
                      <Link to={`/approvals/${approval.data.approval_request.id}`}>Open</Link>
                    </Button>
                  </div>
                  <ol className="mt-3 space-y-1.5">
                    {approval.data.approval_request.steps?.map((s) => (
                      <li key={s.sequence} className="flex items-center gap-2 text-sm">
                        <span className="num w-4 text-content-faint">{s.sequence}</span>
                        <span className="min-w-0 flex-1 truncate text-content-secondary">
                          {s.level.replace(/_/g, " ")}
                        </span>
                        <span className="shrink-0 text-xs" style={{ color: VERSION_STATUS.APPROVED.fg }}>
                          {s.status === "APPROVED" ? "approved" : null}
                        </span>
                        {s.status !== "APPROVED" ? (
                          <span className="shrink-0 text-xs text-content-muted">{s.status.toLowerCase().replace(/_/g, " ")}</span>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </>
              ) : (
                <p className="text-sm text-content-muted">
                  {evaluation.data?.requires_approval
                    ? "This version needs approval but has not been submitted yet."
                    : "No approval has been requested for this version."}
                </p>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead dense icon={<History className="size-4" />} title="Versions" />
            <ul className="divide-y divide-line/70">
              {versions.map((ver) => {
                const current = ver.id === q.current_version_id;
                return (
                  <li key={ver.id} className={cn("px-3.5 py-2.5", current && "bg-accent-50/40")}>
                    <div className="flex items-center gap-2">
                      <span className="font-ui text-sm font-semibold text-content">v{ver.version_number}</span>
                      <VersionStatusBadge value={ver.status} size="sm" />
                      {current ? <span className="ml-auto text-2xs uppercase tracking-wide text-accent-600">Current</span> : null}
                    </div>
                    <div className="mt-1 flex items-baseline justify-between gap-2">
                      <Money value={ver.total_revenue} className="text-sm" />
                      <span className="text-xs text-content-faint">{formatRelative(ver.created_at)}</span>
                    </div>
                    {ver.source && ver.source !== "INITIAL" ? (
                      <p className="mt-0.5 text-2xs text-content-muted">
                        {ver.source.replace(/_/g, " ").toLowerCase()}
                      </p>
                    ) : null}
                    {!current ? (
                      <Link
                        to={`/quotes/${quoteId}/versions/${ver.id}/impact`}
                        className="mt-1 inline-block text-xs text-accent-600 underline-offset-2 hover:underline"
                      >
                        Compare
                      </Link>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </Panel>

          <Panel>
            <PanelHead dense title="Details" />
            <div className="px-3.5 py-1">
              <FieldList>
                <Field label="Deal">{deal.data?.reference ?? "\u2014"}</Field>
                <Field label="Deal name">{deal.data?.name ?? "\u2014"}</Field>
                <Field label="Status">{q.status}</Field>
                <Field label="Created">{formatDateTime(q.created_at)}</Field>
                {v?.valid_until ? <Field label="Valid until">{formatDateTime(v.valid_until)}</Field> : null}
              </FieldList>
            </div>
          </Panel>

          <Panel>
            <PanelHead dense icon={<History className="size-4" />} title="Activity" />
            <div className="max-h-[420px] overflow-y-auto p-3.5">
              <Async
                query={timeline}
                skeleton={<Skeleton className="h-32 w-full" />}
                isEmpty={(d) => d.length === 0}
                empty={<p className="text-sm text-content-muted">No events yet.</p>}
              >
                {(events) => (
                  <Timeline
                    entries={events.map((e) => ({
                      id: e.id,
                      title: e.event_type.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()),
                      actor: e.actor_role ? `${e.actor_role.toLowerCase()}` : undefined,
                      at: formatRelative(e.occurred_at),
                      tone: EVENT_TONE(e.event_type),
                    }))}
                  />
                )}
              </Async>
            </div>
          </Panel>
        </div>
      </div>

      {/* -- revise dialog -------------------------------------------------- */}
      <Dialog
        open={revising}
        onOpenChange={setRevising}
        title="Create a revision"
        description="Supersedes the current version and re-runs policy, risk and approval routing on the new one."
        footer={
          <>
            <Button onClick={() => setRevising(false)}>Cancel</Button>
            <Button
              variant="primary" loading={m.revise.isPending} disabled={!reason.trim()}
              onClick={() =>
                m.revise.mutate({ reason: reason.trim() }, {
                  onSuccess: (nv) => {
                    setRevising(false);
                    setReason("");
                    toast.success(`Version ${nv.version_number} created`);
                    nav(`/quotes/${quoteId}/versions/${nv.id}/build`);
                  },
                  onError: (e) => toast.error(errorTitle(e)),
                })
              }
            >
              Create revision
            </Button>
          </>
        }
      >
        <SectionLabel>Why</SectionLabel>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Customer asked for better pricing on hardware"
          aria-label="Reason for the revision"
          autoFocus
        />
        <GovNote className="mt-3" title="What happens next">
          A new DRAFT version is created and this one becomes SUPERSEDED. Any approval already granted for the
          current version is invalidated if the change is material.
        </GovNote>
      </Dialog>

      {/* -- lose dialog ---------------------------------------------------- */}
      <Dialog
        open={losing}
        onOpenChange={setLosing}
        title="Mark this quotation lost"
        description="Closes the deal. This cannot be undone from the interface."
        width="sm"
        footer={
          <>
            <Button onClick={() => setLosing(false)}>Cancel</Button>
            <Button
              variant="danger" loading={lose.isPending}
              onClick={() =>
                lose.mutate({ reason: reason.trim() || undefined }, {
                  onSuccess: () => { setLosing(false); toast.info("Quotation marked lost"); },
                  onError: toast.fromError,
                })
              }
            >
              Mark lost
            </Button>
          </>
        }
      >
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (optional)"
          aria-label="Reason the quotation was lost"
        />
      </Dialog>
    </Page>
  );
}
