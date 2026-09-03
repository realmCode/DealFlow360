import { Activity, Ban, ChevronDown } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { useAttentionItems, useDealHealth } from "@/api/queries";
import type { DealHealthRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  ATTENTION_LABEL, Async, Badge, BulletGauge, DEAL_STAGE, EmptyState, Metric, Money, Panel,
  PanelHead, Percent, SEVERITY, Score, SectionLabel, Segmented, SeverityBadge, Skeleton,
} from "@/design-system";
import { cn } from "@/lib/cn";

const bandColor = (band: string) =>
  band === "HEALTHY" ? "var(--policy-passed)"
  : band === "WATCH" ? "var(--gov-500)"
  : band === "AT_RISK" ? "var(--risk-high)"
  : "var(--risk-critical)";

/** One deal, expandable to the individual point deductions behind its score. */
function DealRow({ deal }: { deal: DealHealthRead }) {
  const [open, setOpen] = React.useState(false);
  const color = bandColor(deal.health_band);

  return (
    <li className="relative border-b border-line/70 last:border-b-0">
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color }} />
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-4 py-3 pl-4 pr-3 text-left transition-colors hover:bg-accent-50/40"
      >
        <div className="w-14 shrink-0">
          <Score value={deal.health_score} dp={0} className="font-ui text-2xl font-semibold" style={{ color }} />
          <div className="micro">/ 100</div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="num font-ui text-sm font-semibold text-content">{deal.deal_reference}</span>
            <span className="truncate text-sm text-content-secondary">{deal.deal_name}</span>
            <Badge size="sm" tone={DEAL_STAGE[deal.stage]} />
            {deal.blocked ? (
              <Badge size="sm" tone={{ fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: "Blocked" }} />
            ) : null}
          </div>
          <p className="mt-0.5 truncate text-xs text-content-muted">{deal.customer_name}</p>
          <BulletGauge className="mt-2 max-w-md" value={deal.health_score} max={100} color={color} />
        </div>

        <div className="hidden shrink-0 text-right sm:block">
          <Money value={deal.total_value} className="text-sm font-semibold" />
          <div className="text-xs text-content-muted"><Percent value={deal.margin_pct} dp={1} /> margin</div>
        </div>

        <div className="hidden shrink-0 text-right lg:block">
          <div className="num text-sm font-semibold text-content">{deal.signals?.length ?? 0}</div>
          <div className="micro">signals</div>
        </div>

        <ChevronDown className={cn("size-4 shrink-0 text-content-faint transition-transform duration-fast", open && "rotate-180")} />
      </button>

      {open ? (
        <div className="border-t border-line/70 bg-surface-sunken px-4 py-3">
          <p className="mb-3 text-sm leading-[19px] text-content-secondary">{deal.summary}</p>
          {(deal.signals?.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No deductions — this deal scores full marks.</p>
          ) : (
            <ul className="space-y-2">
              {deal.signals!.map((s, i) => (
                <li key={`${s.code}-${i}`} className="flex items-start gap-3 rounded-md border border-line bg-surface px-3 py-2">
                  <SeverityBadge value={s.severity} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="font-ui text-xs font-semibold text-content">{s.label}</p>
                    <p className="mt-0.5 text-sm leading-[18px] text-content-secondary">{s.detail}</p>
                  </div>
                  <span
                    className="num shrink-0 text-sm font-semibold"
                    style={{ color: SEVERITY[s.severity].fg }}
                    title="Points deducted from the health score"
                  >
                    &minus;<Score value={s.points} dp={0} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex gap-2">
            <Link to="/attention" className="text-xs text-accent-600 underline-offset-2 hover:underline">
              {deal.open_attention_items} open attention item(s)
            </Link>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function DealHealthPage() {
  const health = useDealHealth();
  const attention = useAttentionItems({ status: "OPEN" });
  const [scope, setScope] = React.useState<"all" | "risk">("all");

  const deals = React.useMemo(() => {
    const rows = [...(health.data?.deals ?? [])].sort((a, b) => a.health_score - b.health_score);
    return scope === "risk" ? rows.filter((d) => d.blocked || d.health_score < 70) : rows;
  }, [health.data, scope]);

  const items = attention.data ?? [];
  const countBy = (t: string) => items.filter((i) => i.type === t).length;

  /* The three cards the wireframe shows, each backed by a real attention type. */
  const CARDS = [
    { type: "STALLED_DEAL", label: "Stalled deals", hint: "no movement past the configured window" },
    { type: "DISCOUNT_ANOMALY", label: "Discount anomalies", hint: "above the rep's own historical average" },
    { type: "DELIVERY_SLIPPAGE", label: "Delivery slippage", hint: "promise dates at risk" },
    { type: "APPROVAL_SLA_BREACH", label: "Approval bottlenecks", hint: "past the approval SLA" },
  ];

  const atRisk = (health.data?.deals ?? []).filter((d) => d.blocked || d.health_score < 70).length;

  return (
    <Page
      title="Deal health"
      subtitle="A deterministic score per deal, with every deduction itemised."
    >
      <div className="mb-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <Panel rail="var(--accent-500)" className="px-3.5 py-2.5">
          {health.isPending ? (
            <Skeleton className="h-10 w-24" />
          ) : (
            <Metric label="Average health" size="lg" hint={`${health.data?.deals.length ?? 0} deals scored`}>
              <Score value={health.data?.average_health ?? 0} dp={0} />
            </Metric>
          )}
        </Panel>
        {CARDS.map((c) => {
          const n = countBy(c.type);
          return (
            <Panel key={c.type} rail={n ? "var(--risk-high)" : undefined} className="px-3.5 py-2.5">
              <Metric label={c.label} size="lg" hint={c.hint} tone={n ? "var(--risk-high)" : "var(--ink-400)"}>
                {n}
              </Metric>
            </Panel>
          );
        })}
      </div>

      <Panel>
        <PanelHead
          icon={<Activity className="size-4" />}
          title="Deals, worst first"
          subtitle="Expand a row to see the points behind the score"
          actions={
            <Segmented
              ariaLabel="Health filter"
              value={scope}
              onValueChange={setScope}
              options={[
                { value: "all", label: "All", count: health.data?.deals.length },
                { value: "risk", label: "Needs attention", count: atRisk },
              ]}
            />
          }
        />
        <Async
          query={health}
          skeleton={<div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>}
          isEmpty={() => deals.length === 0}
          empty={
            <EmptyState
              icon={<Ban className="size-5" />}
              title={scope === "risk" ? "Every deal is healthy" : "No deals scored yet"}
              body={scope === "risk" ? "Nothing is blocked and nothing scores below 70." : undefined}
            />
          }
        >
          {() => <ul>{deals.map((d) => <DealRow key={d.deal_id} deal={d} />)}</ul>}
        </Async>
      </Panel>

      {items.length > 0 ? (
        <>
          <SectionLabel className="mt-4">Open signals by type</SectionLabel>
          <div className="flex flex-wrap gap-2">
            {Object.entries(
              items.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.type]: (acc[i.type] ?? 0) + 1 }), {}),
            )
              .sort((a, b) => b[1] - a[1])
              .map(([type, n]) => (
                <Link
                  key={type}
                  to="/attention"
                  className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-1.5 transition-colors hover:border-accent-400"
                >
                  <span className="text-sm text-content-secondary">
                    {ATTENTION_LABEL[type as keyof typeof ATTENTION_LABEL] ?? type}
                  </span>
                  <span className="num text-sm font-semibold text-content">{n}</span>
                </Link>
              ))}
          </div>
        </>
      ) : null}
    </Page>
  );
}
