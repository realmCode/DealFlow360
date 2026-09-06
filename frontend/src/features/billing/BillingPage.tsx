import { Receipt, Repeat } from "lucide-react";
import * as React from "react";
import { dec, formatDate, sortKey } from "@/api/money";
import { useSchedules } from "@/api/queries";
import type { BillingScheduleRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, type Column, DataTable, EmptyState, Metric, Money, Panel, SearchInput,
  Segmented, SplitBar,
} from "@/design-system";

const SCHEDULE_TONE: Record<string, { fg: string; bg: string; label: string }> = {
  SCHEDULED: { fg: "var(--state-draft)", bg: "var(--state-draft-bg)", label: "Scheduled" },
  ACTIVE: { fg: "var(--state-sent)", bg: "var(--state-sent-bg)", label: "Active" },
  INVOICED: { fg: "var(--state-pending)", bg: "var(--state-pending-bg)", label: "Invoiced" },
  COMPLETED: { fg: "var(--state-confirmed)", bg: "var(--state-confirmed-bg)", label: "Completed" },
  CANCELLED: { fg: "var(--state-superseded)", bg: "var(--state-superseded-bg)", label: "Cancelled" },
};

export function BillingPage() {
  const query = useSchedules();
  const [search, setSearch] = React.useState("");
  const [kind, setKind] = React.useState<"all" | "ONE_TIME" | "RECURRING">("all");

  const data = query.data;
  const all = React.useMemo(() => data ?? [], [data]);
  const rows = React.useMemo(() => {
    const term = search.trim().toLowerCase();
    return all.filter((s) => {
      if (kind !== "all" && s.billing_type !== kind) return false;
      if (!term) return true;
      return s.schedule_number.toLowerCase().includes(term) || (s.description ?? "").toLowerCase().includes(term);
    });
  }, [all, search, kind]);

  const oneTime = all.filter((s) => s.billing_type === "ONE_TIME");
  const recurring = all.filter((s) => s.billing_type === "RECURRING");
  const sum = (xs: BillingScheduleRead[]) => xs.reduce((t, s) => t.plus(dec(s.total_amount)), dec(0)).toString();

  const columns: Column<BillingScheduleRead>[] = [
    {
      id: "schedule",
      header: "Schedule",
      sortValue: (s) => s.schedule_number,
      cell: (s) => (
        <div>
          <div className="num font-medium text-content">{s.schedule_number}</div>
          <div className="truncate text-2xs text-content-faint">{s.description}</div>
        </div>
      ),
    },
    {
      id: "type",
      header: "Type",
      sortValue: (s) => s.billing_type,
      cell: (s) =>
        s.billing_type === "RECURRING" ? (
          <span className="inline-flex items-center gap-1.5 rounded-sm bg-[var(--state-negotiating-bg)] px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wide text-[var(--state-negotiating)]">
            <Repeat className="size-3" /> {s.recurring_interval}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-sm bg-accent-100 px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wide text-accent-700">
            One-time
          </span>
        ),
    },
    { id: "status", header: "Status", sortValue: (s) => s.status, cell: (s) => <Badge size="sm" tone={SCHEDULE_TONE[s.status]} /> },
    {
      id: "period",
      header: "Period",
      cell: (s) => (
        <span className="whitespace-nowrap text-xs text-content-muted">
          {formatDate(s.period_start)} &ndash; {formatDate(s.period_end)}
          {s.total_periods > 1 ? <span className="num"> ({s.period_number}/{s.total_periods})</span> : null}
        </span>
      ),
      hideBelow: "lg",
    },
    { id: "due", header: "Due", sortValue: (s) => s.due_date ?? "", cell: (s) => <span className="whitespace-nowrap text-xs">{formatDate(s.due_date)}</span>, hideBelow: "md" },
    {
      id: "prorated",
      header: "Prorated",
      align: "center",
      cell: (s) => (s.is_prorated ? <span className="num text-xs text-gov-600">×{dec(s.proration_factor).toFixed(4)}</span> : <span className="text-content-faint">—</span>),
      hideBelow: "xl",
    },
    { id: "amount", header: "Amount", align: "right", sortValue: (s) => sortKey(s.total_amount), cell: (s) => <Money value={s.total_amount} currency={s.currency} className="font-semibold" /> },
  ];

  return (
    <Page title="Billing schedules" subtitle="One-time and recurring schedules coexist on the same order.">
      <div className="mb-3 grid gap-2 sm:grid-cols-3">
        <Panel rail="var(--accent-500)" className="px-3.5 py-2.5">
          <Metric label="One-time" size="lg" hint={`${oneTime.length} schedules`}>
            <Money value={sum(oneTime)} />
          </Metric>
        </Panel>
        <Panel rail="var(--state-negotiating)" className="px-3.5 py-2.5">
          <Metric label="Recurring" size="lg" hint={`${recurring.length} schedules`}>
            <Money value={sum(recurring)} />
          </Metric>
        </Panel>
        <Panel className="px-3.5 py-2.5">
          <div className="micro">Mix</div>
          <SplitBar
            className="mt-2"
            height={10}
            segments={[
              { id: "o", label: "One-time", value: dec(sum(oneTime)).toNumber(), color: "var(--accent-500)", caption: String(oneTime.length) },
              { id: "r", label: "Recurring", value: dec(sum(recurring)).toNumber(), color: "var(--state-negotiating)", caption: String(recurring.length) },
            ]}
          />
        </Panel>
      </div>

      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput value={search} onValueChange={setSearch} placeholder="Search schedule or description" className="w-full max-w-xs" />
          <Segmented
            ariaLabel="Billing type"
            value={kind}
            onValueChange={setKind}
            options={[
              { value: "all", label: "All", count: all.length },
              { value: "ONE_TIME", label: "One-time", count: oneTime.length },
              { value: "RECURRING", label: "Recurring", count: recurring.length },
            ]}
          />
        </div>
        <Async
          query={query}
          isEmpty={() => rows.length === 0}
          empty={<EmptyState icon={<Receipt className="size-5" />} title="No billing schedules" body="Schedules are generated when a customer confirms an order." />}
        >
          {() => (
            <DataTable
              rows={rows}
              columns={columns}
              caption="Billing schedules"
              getKey={(s) => s.id}
              rail={(s) => (s.billing_type === "RECURRING" ? "var(--state-negotiating)" : "var(--accent-500)")}
            />
          )}
        </Async>
      </Panel>
    </Page>
  );
}
