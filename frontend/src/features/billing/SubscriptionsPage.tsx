import { Repeat } from "lucide-react";
import * as React from "react";
import { formatDate, sortKey } from "@/api/money";
import { useBillingMutations, useSchedules } from "@/api/queries";
import type { BillingScheduleRead, SubscriptionChangeResult } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, Button, type Column, DataTable, Dialog, EmptyState, FormField, GovNote,
  Input, Money, NumericInput, Panel, SectionLabel, toast,
} from "@/design-system";

/**
 * The wireframe shows an "Active / Paused / Cancelled" chip row. The backend's
 * BillingScheduleStatus has no PAUSED, so it is not offered — a pause control
 * that cannot pause anything would be fake.
 */
const TONE: Record<string, { fg: string; bg: string; label: string }> = {
  SCHEDULED: { fg: "var(--state-draft)", bg: "var(--state-draft-bg)", label: "Scheduled" },
  ACTIVE: { fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Active" },
  INVOICED: { fg: "var(--state-pending)", bg: "var(--state-pending-bg)", label: "Invoiced" },
  COMPLETED: { fg: "var(--state-confirmed)", bg: "var(--state-confirmed-bg)", label: "Completed" },
  CANCELLED: { fg: "var(--state-superseded)", bg: "var(--state-superseded-bg)", label: "Cancelled" },
};

export function SubscriptionsPage() {
  const can = useCan();
  const query = useSchedules();
  const { cancelSubscription, changeSubscription } = useBillingMutations();
  const [target, setTarget] = React.useState<{ row: BillingScheduleRead; mode: "cancel" | "change" } | null>(null);
  const [effective, setEffective] = React.useState("");
  const [quantity, setQuantity] = React.useState("");
  const [outcome, setOutcome] = React.useState<SubscriptionChangeResult | null>(null);

  const subs = (query.data ?? []).filter((s) => s.billing_type === "RECURRING");
  const byStatus = (st: string) => subs.filter((s) => s.status === st).length;

  const columns: Column<BillingScheduleRead>[] = [
    {
      id: "plan",
      header: "Plan",
      sortValue: (s) => s.description ?? "",
      cell: (s) => (
        <div>
          <div className="font-medium text-content">{s.description}</div>
          <div className="num text-2xs text-content-faint">{s.schedule_number}</div>
        </div>
      ),
    },
    { id: "cycle", header: "Cycle", sortValue: (s) => s.recurring_interval ?? "", cell: (s) => <span className="capitalize">{s.recurring_interval?.toLowerCase()}</span> },
    { id: "status", header: "Status", sortValue: (s) => s.status, cell: (s) => <Badge size="sm" tone={TONE[s.status]} /> },
    { id: "period", header: "Current period", cell: (s) => <span className="whitespace-nowrap text-xs text-content-muted">{formatDate(s.period_start)} &ndash; {formatDate(s.period_end)}</span>, hideBelow: "md" },
    { id: "next", header: "Next bill", sortValue: (s) => s.due_date ?? "", cell: (s) => <span className="whitespace-nowrap text-xs">{formatDate(s.due_date)}</span> },
    { id: "amount", header: "Per period", align: "right", sortValue: (s) => sortKey(s.total_amount), cell: (s) => <Money value={s.total_amount} currency={s.currency} className="font-semibold" /> },
    ...(can.billing
      ? [{
          id: "actions",
          header: "",
          align: "right" as const,
          cell: (s: BillingScheduleRead) =>
            ["SCHEDULED", "ACTIVE"].includes(s.status) ? (
              <span className="flex justify-end gap-1">
                <Button size="xs" variant="ghost" onClick={() => { setTarget({ row: s, mode: "change" }); setEffective(s.period_start ?? ""); setQuantity("1"); setOutcome(null); }}>
                  Change
                </Button>
                <Button size="xs" variant="ghost" onClick={() => { setTarget({ row: s, mode: "cancel" }); setEffective(s.period_start ?? ""); setOutcome(null); }}>
                  Cancel
                </Button>
              </span>
            ) : null,
        }]
      : []),
  ];

  const busy = cancelSubscription.isPending || changeSubscription.isPending;

  return (
    <Page title="Subscriptions" subtitle="Every recurring plan, regardless of which order it came from.">
      <div className="mb-3 flex flex-wrap gap-2">
        {["SCHEDULED", "ACTIVE", "INVOICED", "COMPLETED", "CANCELLED"].map((st) => (
          <span key={st} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-1.5">
            <span aria-hidden className="size-1.5 rounded-full" style={{ background: TONE[st].fg }} />
            <span className="text-sm text-content-secondary">{TONE[st].label}</span>
            <span className="num text-sm font-semibold text-content">{byStatus(st)}</span>
          </span>
        ))}
      </div>

      <Panel>
        <Async
          query={query}
          isEmpty={() => subs.length === 0}
          empty={<EmptyState icon={<Repeat className="size-5" />} title="No subscriptions" body="Recurring schedules appear once an order containing a subscription product is confirmed." />}
        >
          {() => <DataTable rows={subs} columns={columns} caption="Subscriptions" getKey={(s) => s.id} rail={(s) => TONE[s.status].fg} />}
        </Async>
      </Panel>

      <Dialog
        open={target !== null}
        onOpenChange={(v) => { if (!v) { setTarget(null); setOutcome(null); } }}
        title={target?.mode === "cancel" ? "Cancel subscription" : "Change subscription"}
        description={
          target?.mode === "cancel"
            ? "The unused portion of the current period is credited back."
            : "Quantity changes are prorated across the remainder of the period."
        }
        footer={
          outcome ? (
            <Button variant="primary" onClick={() => { setTarget(null); setOutcome(null); }}>Done</Button>
          ) : (
            <>
              <Button onClick={() => setTarget(null)}>Cancel</Button>
              <Button
                variant={target?.mode === "cancel" ? "danger" : "primary"}
                loading={busy}
                disabled={!effective}
                onClick={() => {
                  if (!target) return;
                  const opts = {
                    onSuccess: (res: SubscriptionChangeResult) => { setOutcome(res); toast.success("Applied"); },
                    onError: toast.fromError,
                  };
                  if (target.mode === "cancel") {
                    cancelSubscription.mutate({ scheduleId: target.row.id, body: { effective_date: effective } }, opts);
                  } else {
                    changeSubscription.mutate(
                      { scheduleId: target.row.id, body: { effective_date: effective, new_quantity: quantity } },
                      opts,
                    );
                  }
                }}
              >
                {target?.mode === "cancel" ? "Cancel subscription" : "Apply change"}
              </Button>
            </>
          )
        }
      >
        {outcome ? (
          <div className="space-y-3">
            <GovNote title="What the engine did">{outcome.explanation}</GovNote>
            <dl className="grid grid-cols-2 gap-3">
              <div><dt className="micro">Periods kept</dt><dd className="num text-md font-semibold">{outcome.periods_kept}</dd></div>
              <div><dt className="micro">Regenerated</dt><dd className="num text-md font-semibold">{outcome.periods_regenerated}</dd></div>
              <div><dt className="micro">Credit</dt><dd><Money value={outcome.proration_credit} className="text-md font-semibold" /></dd></div>
              <div><dt className="micro">Charge</dt><dd><Money value={outcome.proration_charge} className="text-md font-semibold" /></dd></div>
            </dl>
          </div>
        ) : (
          <div className="space-y-3">
            <FormField label="Effective date" required hint="Must fall inside the current period.">
              {(p) => <Input {...p} type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />}
            </FormField>
            {target?.mode === "change" ? (
              <FormField label="New quantity" required>
                {(p) => <NumericInput id={p.id} value={quantity} onValueChange={setQuantity} />}
              </FormField>
            ) : null}
            {target ? (
              <>
                <SectionLabel className="mt-4">Current</SectionLabel>
                <p className="text-sm text-content-secondary">
                  {target.row.description} &middot; <Money value={target.row.total_amount} currency={target.row.currency} /> per{" "}
                  {target.row.recurring_interval?.toLowerCase()} &middot; period{" "}
                  {formatDate(target.row.period_start)} to {formatDate(target.row.period_end)}
                </p>
              </>
            ) : null}
          </div>
        )}
      </Dialog>
    </Page>
  );
}
