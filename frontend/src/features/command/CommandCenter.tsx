import {
  ArrowRight, Bell, CheckCircle2, ChevronRight, Gauge, Inbox, ShieldAlert, Sparkles, TrendingUp,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useApprovalInbox, useAttentionAction, useControlTower, useDealHealth,
} from "@/api/queries";
import type { AttentionItemRead, Severity } from "@/api/types";
import { useAuth, useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  ATTENTION_LABEL, Async, Badge, BulletGauge, Button, EmptyState, ErrorState, Metric, Money,
  Panel, PanelHead, Percent, RiskBadge, SEVERITY, Score, SectionLabel, SeverityBadge,
  Skeleton, SkeletonMetrics, toast,
} from "@/design-system";
import { formatRelative, riskBandFor } from "@/api/money";
import { cn } from "@/lib/cn";

const SEV_ORDER: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

/** Where an attention item should take you. Derived from what the item is about. */
function targetFor(item: AttentionItemRead): string | null {
  if (item.source_type === "approval_request") return `/approvals/${item.source_id}`;
  if (item.quote_id) return `/quotes/${item.quote_id}`;
  if (item.source_type === "sales_order") return `/orders/${item.source_id}`;
  if (item.deal_id) return `/deals`;
  return null;
}

/**
 * An attention row states what, why, the impact and the next action — the four
 * questions §18 requires. All four come from the payload; none is invented.
 */
function AttentionRow({ item, onAction }: { item: AttentionItemRead; onAction: () => void }) {
  const nav = useNavigate();
  const tone = SEVERITY[item.severity];
  const to = targetFor(item);
  const act = useAttentionAction();

  return (
    <article
      className={cn(
        "group relative grid gap-x-4 gap-y-2 border-b border-line/70 py-3 pl-4 pr-3 last:border-b-0",
        "transition-colors duration-fast hover:bg-accent-50/50",
        to && "cursor-pointer",
      )}
      onClick={to ? () => nav(to) : undefined}
      role={to ? "link" : undefined}
      tabIndex={to ? 0 : undefined}
      onKeyDown={
        to
          ? (e) => {
              if (e.key === "Enter") nav(to);
            }
          : undefined
      }
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: tone.fg }} />

      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge value={item.severity} size="sm" />
        <span className="font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint">
          {ATTENTION_LABEL[item.type]}
        </span>
        <span className="ml-auto shrink-0 text-xs text-content-faint">{formatRelative(item.created_at)}</span>
      </div>

      <div>
        <h3 className="font-ui text-md font-semibold leading-snug text-content">{item.title}</h3>

        <dl className="mt-1.5 space-y-1">
          <div className="flex gap-2 text-sm leading-[18px]">
            <dt className="w-14 shrink-0 text-content-faint">Why</dt>
            <dd className="min-w-0 text-content-secondary">{item.reason}</dd>
          </div>
          <div className="flex gap-2 text-sm leading-[18px]">
            <dt className="w-14 shrink-0 text-content-faint">Impact</dt>
            <dd className="min-w-0 text-content-secondary">{item.impact}</dd>
          </div>
          <div className="flex gap-2 text-sm leading-[18px]">
            <dt className="w-14 shrink-0 text-content-faint">Do</dt>
            <dd className="min-w-0 font-medium text-content">{item.recommended_action}</dd>
          </div>
        </dl>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {item.owner_role ? (
          <span className="rounded-sm border border-line bg-surface-sunken px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wider text-content-muted">
            {item.owner_role}
          </span>
        ) : null}
        <div className="ml-auto flex items-center gap-1.5 opacity-0 transition-opacity duration-fast group-hover:opacity-100 focus-within:opacity-100">
          {item.status === "OPEN" ? (
            <Button
              size="xs" variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                act.mutate(
                  { id: item.id, action: "acknowledge" },
                  {
                    onSuccess: () => {
                      toast.success("Acknowledged", item.title);
                      onAction();
                    },
                    onError: toast.fromError,
                  },
                );
              }}
            >
              Acknowledge
            </Button>
          ) : null}
          {to ? (
            <Button size="xs" variant="secondary" icon={<ArrowRight className="size-3" />}>
              Open
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function CommandCenter() {
  const { user } = useAuth();
  const can = useCan();
  const tower = useControlTower();
  const health = useDealHealth();
  const inbox = useApprovalInbox(can.approve);

  const [scope, setScope] = React.useState<"mine" | "all">("mine");

  const counts = tower.data?.counts;
  const myQueue = tower.data?.my_queue ?? [];
  const allItems = React.useMemo(
    () => (tower.data?.groups ?? []).flatMap((g) => g.items ?? []),
    [tower.data],
  );
  const shown = scope === "mine" && myQueue.length > 0 ? myQueue : allItems;

  const worst = React.useMemo(
    () => [...(health.data?.deals ?? [])].sort((a, b) => a.health_score - b.health_score).slice(0, 5),
    [health.data],
  );

  const firstName = user?.full_name?.split(" ")[0] ?? "there";

  return (
    <Page
      title="Command Center"
      subtitle={
        tower.data?.headline ??
        "The ranked queue of everything that needs a decision right now."
      }
      actions={
        can.authorQuotes ? (
          <Button variant="primary" asChild icon={<Sparkles className="size-3.5" />}>
            <Link to="/quotes">New quotation</Link>
          </Button>
        ) : null
      }
    >
      {/* -- severity ledger ------------------------------------------------ */}
      {tower.isPending ? (
        <SkeletonMetrics count={5} />
      ) : tower.isError ? (
        <Panel><ErrorState error={tower.error} onRetry={tower.refetch} compact /></Panel>
      ) : (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
          {SEV_ORDER.map((sev) => {
            const n = (counts?.[sev.toLowerCase() as keyof typeof counts] as number) ?? 0;
            const tone = SEVERITY[sev];
            return (
              <Panel key={sev} rail={n > 0 ? tone.fg : "var(--ink-200)"} className="px-3.5 py-2.5">
                <Metric
                  label={`${tone.label} severity`}
                  size="lg"
                  tone={n > 0 ? tone.fg : "var(--ink-400)"}
                >
                  {n}
                </Metric>
              </Panel>
            );
          })}
          <Panel rail="var(--accent-500)" className="px-3.5 py-2.5">
            <Metric label="Open in total" size="lg">
              {counts?.total_open ?? 0}
            </Metric>
          </Panel>
        </div>
      )}

      <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* -- the queue --------------------------------------------------- */}
        <Panel className="min-w-0">
          <PanelHead
            icon={<Bell className="size-4" />}
            title="Action queue"
            subtitle="Severity first. Every item states why it fired, what it costs, and what to do."
            actions={
              myQueue.length > 0 ? (
                <div className="inline-flex items-center gap-0.5 rounded-md border border-line bg-ink-50 p-0.5">
                  {(["mine", "all"] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setScope(s)}
                      className={cn(
                        "inline-flex h-6 cursor-pointer items-center gap-1.5 rounded-sm px-2.5 font-ui text-xs font-medium transition-colors",
                        scope === s ? "bg-white text-content shadow-[0_1px_2px_rgb(16_24_40/0.08)]" : "text-content-muted hover:text-content",
                      )}
                    >
                      {s === "mine" ? "Assigned to me" : "Everything"}
                      <span className="num text-2xs text-content-faint">
                        {s === "mine" ? myQueue.length : allItems.length}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null
            }
          />
          {tower.isPending ? (
            <div className="space-y-3 p-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-3 w-32" />
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-3 w-full" />
                </div>
              ))}
            </div>
          ) : shown.length === 0 ? (
            <EmptyState
              icon={<CheckCircle2 className="size-5" />}
              title="Nothing needs your attention"
              body={`Every deal is inside policy, ${firstName}. New signals appear here the moment the engine raises them.`}
            />
          ) : (
            <div>
              {shown.map((item) => (
                <AttentionRow key={item.id} item={item} onAction={() => tower.refetch()} />
              ))}
            </div>
          )}
        </Panel>

        {/* -- side rail ---------------------------------------------------- */}
        <div className="min-w-0 space-y-3">
          {can.approve ? (
            <Panel>
              <PanelHead
                icon={<Inbox className="size-4" />}
                title="Awaiting your decision"
                dense
                actions={
                  <Button size="xs" variant="ghost" asChild icon={<ChevronRight className="size-3" />}>
                    <Link to="/approvals">Inbox</Link>
                  </Button>
                }
              />
              {inbox.isPending ? (
                <div className="space-y-2 p-3">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : (inbox.data?.length ?? 0) === 0 ? (
                <EmptyState compact icon={<CheckCircle2 className="size-5" />} title="Inbox clear" />
              ) : (
                <ul className="divide-y divide-line/70">
                  {inbox.data!.slice(0, 5).map((a) => (
                    <li key={a.approval_step_id}>
                      <Link
                        to={`/approvals/${a.approval_request_id}`}
                        className="block px-3 py-2.5 transition-colors hover:bg-accent-50/60"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-ui text-sm font-semibold text-content">{a.quote_number}</span>
                          <span className="text-xs text-content-muted">v{a.version_number}</span>
                          {a.is_reapproval ? (
                            <Badge size="sm" tone={{ fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: "Re-approval" }} />
                          ) : null}
                          <span className="ml-auto shrink-0 text-xs text-content-faint">
                            {formatRelative(a.waiting_since)}
                          </span>
                        </div>
                        <p className="mt-0.5 truncate text-sm text-content-secondary">{a.customer_name}</p>
                        <div className="mt-1.5 flex items-center gap-3">
                          <Money value={a.total_revenue} className="text-sm font-semibold" />
                          <Percent value={a.margin_pct} className="text-xs text-content-muted" />
                          <RiskBadge value={riskBandFor(a.blended_risk_score)} size="sm" />
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          ) : null}

          <Panel>
            <PanelHead
              icon={<Gauge className="size-4" />}
              title="Deal health"
              dense
              subtitle={
                health.data ? `Average ${health.data.average_health}/100 across ${health.data.deals.length} deals` : undefined
              }
              actions={
                <Button size="xs" variant="ghost" asChild icon={<ChevronRight className="size-3" />}>
                  <Link to="/deal-health">All</Link>
                </Button>
              }
            />
            <Async
              query={health}
              skeleton={<div className="space-y-2 p-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>}
              isEmpty={(d) => d.deals.length === 0}
              empty={<EmptyState compact title="No deals yet" />}
            >
              {() => (
                <ul className="divide-y divide-line/70">
                  {worst.map((d) => {
                    const color =
                      d.health_score >= 80 ? "var(--policy-passed)"
                      : d.health_score >= 50 ? "var(--gov-500)"
                      : "var(--policy-violated)";
                    return (
                      <li key={d.deal_id} className="px-3 py-2.5">
                        <div className="flex items-baseline gap-2">
                          <span className="truncate font-ui text-sm font-medium text-content">{d.deal_reference}</span>
                          <span className="truncate text-xs text-content-muted">{d.customer_name}</span>
                          <span className="num ml-auto shrink-0 text-sm font-semibold" style={{ color }}>
                            <Score value={d.health_score} dp={0} />
                          </span>
                        </div>
                        <BulletGauge className="mt-1.5" value={d.health_score} max={100} color={color} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </Async>
          </Panel>

          <Panel>
            <PanelHead icon={<TrendingUp className="size-4" />} title="Signal mix" dense />
            <div className="p-3">
              {tower.data && Object.keys(tower.data.by_type ?? {}).length > 0 ? (
                <ul className="space-y-1.5">
                  {Object.entries(tower.data.by_type as Record<string, number>)
                    .sort((a, b) => b[1] - a[1])
                    .map(([type, n]) => (
                      <li key={type} className="flex items-center gap-2">
                        <ShieldAlert aria-hidden className="size-3.5 shrink-0 text-content-faint" />
                        <span className="min-w-0 truncate text-sm text-content-secondary">
                          {ATTENTION_LABEL[type as keyof typeof ATTENTION_LABEL] ?? type}
                        </span>
                        <span className="num ml-auto text-sm font-semibold text-content">{n}</span>
                      </li>
                    ))}
                </ul>
              ) : (
                <p className="text-sm text-content-muted">No open signals.</p>
              )}
            </div>
          </Panel>
        </div>
      </div>

      <SectionLabel className="mt-4">Generated {formatRelative(tower.data?.generated_at)}</SectionLabel>
    </Page>
  );
}
