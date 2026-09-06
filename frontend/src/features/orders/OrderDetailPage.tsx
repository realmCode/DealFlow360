import { ArrowLeft, CalendarClock, PackageCheck, Split, Truck, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { dec, formatDate, formatDateTime } from "@/api/money";
import { idempotencyKey } from "@/api/client";
import { useAllocations, useBillingSummary, useOrder, useOrderMutations } from "@/api/queries";
import type { AllocationResult } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Button, Dialog, ErrorState, Field, FieldList, GovNote, Input, Money,
  OrderStatusBadge, Panel, PanelHead, Percent, Qty, SectionLabel, Skeleton, SplitBar,
  toast, Tooltip,
} from "@/design-system";
import { cn } from "@/lib/cn";

/** Distinct colour per warehouse in the split bars, plus a fixed backorder red. */
const WAREHOUSE_COLORS = ["var(--accent-500)", "var(--state-negotiating)", "var(--policy-passed)", "var(--gov-500)"];
const BACKORDER_COLOR = "var(--risk-high)";

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const can = useCan();
  const order = useOrder(orderId);
  const allocations = useAllocations(orderId);
  const billing = useBillingSummary(orderId);
  const m = useOrderMutations(orderId!);

  const [result, setResult] = React.useState<AllocationResult | null>(null);
  const [allowPartial, setAllowPartial] = React.useState(false);
  const [promising, setPromising] = React.useState(false);
  const [promiseDate, setPromiseDate] = React.useState("");
  const [cancelling, setCancelling] = React.useState(false);
  const intent = React.useRef(idempotencyKey("allocate"));

  if (order.isPending) {
    return (
      <Page title={<Skeleton className="h-7 w-56" />}>
        <Skeleton className="h-64 w-full rounded-lg" />
      </Page>
    );
  }
  if (order.isError) {
    return (
      <Page title="Order">
        <Panel><ErrorState error={order.error} onRetry={order.refetch} /></Panel>
      </Page>
    );
  }

  const o = order.data!;
  const lines = result?.lines ?? allocations.data ?? [];
  const warehouseColor = new Map<string, string>();
  let ci = 0;
  for (const l of lines) {
    for (const s of l.splits ?? []) {
      if (s.warehouse_code === "BACKORDER") continue;
      if (!warehouseColor.has(s.warehouse_code)) {
        warehouseColor.set(s.warehouse_code, WAREHOUSE_COLORS[ci % WAREHOUSE_COLORS.length]);
        ci++;
      }
    }
  }

  const canAllocate = can.allocate && ["CREATED", "PARTIALLY_ALLOCATED", "BACKORDERED"].includes(o.status);
  const canFulfill = can.fulfill && ["ALLOCATED", "PARTIALLY_ALLOCATED", "PARTIALLY_FULFILLED"].includes(o.status);

  return (
    <Page
      title={
        <span className="flex flex-wrap items-center gap-2.5">
          <span className="num">{o.order_number}</span>
          <OrderStatusBadge value={o.status} />
        </span>
      }
      subtitle={
        <span className="flex flex-wrap items-center gap-2">
          <Link to="/orders" className="inline-flex items-center gap-1 hover:text-content">
            <ArrowLeft className="size-3.5" /> Orders
          </Link>
          <span className="text-content-faint">/</span>
          <span>{o.customer_name}</span>
        </span>
      }
      actions={
        <>
          {can.promise ? (
            <Button icon={<CalendarClock className="size-3.5" />} onClick={() => setPromising(true)}>
              {o.promised_delivery_date ? "Revise promise" : "Set promise date"}
            </Button>
          ) : null}
          {canAllocate ? (
            <Button
              variant="primary"
              icon={<Split className="size-3.5" />}
              loading={m.allocate.isPending}
              onClick={() =>
                m.allocate.mutate(
                  { body: { allow_partial: allowPartial }, key: intent.current },
                  {
                    onSuccess: (res) => {
                      setResult(res);
                      toast.success(res.message ?? "Stock allocated");
                    },
                    onError: (e) => {
                      toast.fromError(e);
                      setAllowPartial(true);
                    },
                  },
                )
              }
            >
              Allocate stock
            </Button>
          ) : null}
          {canFulfill ? (
            <Button
              variant="approve"
              icon={<Truck className="size-3.5" />}
              loading={m.fulfill.isPending}
              onClick={() =>
                m.fulfill.mutate(undefined, {
                  onSuccess: () => toast.success("Shipment created", "One fulfilment per warehouse."),
                  onError: toast.fromError,
                })
              }
            >
              Ship allocated stock
            </Button>
          ) : null}
          {can.allocate && !["FULFILLED", "CANCELLED"].includes(o.status) ? (
            <Button variant="ghost" icon={<XCircle className="size-3.5" />} onClick={() => setCancelling(true)}>
              Cancel
            </Button>
          ) : null}
        </>
      }
    >
      {result?.message ? (
        <GovNote
          className="mb-3"
          tone={result.has_backorder ? "critical" : "governance"}
          title="Allocation result"
          icon={<Split className="size-3.5" />}
        >
          {result.message} Estimated shipping cost{" "}
          <span className="num font-semibold">
            <Money value={result.estimated_shipping_cost} currency={o.currency} />
          </span>{" "}
          across <span className="num font-semibold">{result.shipment_count}</span> shipment
          {result.shipment_count === 1 ? "" : "s"}.
        </GovNote>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-3">
          {/* -- allocation, the flagship view ------------------------------ */}
          <Panel>
            <PanelHead
              title="Warehouse allocation"
              subtitle="Where each line is sourced from, and why"
              actions={
                lines.length > 0 ? (
                  <span className="num text-xs text-content-muted">
                    {result?.shipment_count ?? new Set(lines.flatMap((l) => (l.splits ?? []).map((s) => s.warehouse_code))).size} shipment(s)
                  </span>
                ) : null
              }
            />
            {lines.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <p className="font-ui text-md font-medium text-content">Nothing allocated yet</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-content-muted">
                  Allocating reserves stock across warehouses by priority and shipping cost. The split is
                  computed by the backend, not chosen here.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {lines.map((l) => {
                  const segments = (l.splits ?? []).map((s) => ({
                    id: `${l.sales_order_line_id}-${s.warehouse_code}`,
                    label: s.warehouse_code === "BACKORDER" ? "Backorder" : s.warehouse_name,
                    value: dec(s.quantity).toNumber(),
                    color: s.warehouse_code === "BACKORDER" ? BACKORDER_COLOR : (warehouseColor.get(s.warehouse_code) ?? "var(--ink-400)"),
                    caption: dec(s.quantity).toFixed(0),
                  }));
                  const backordered = dec(l.quantity_backordered).greaterThan(0);
                  return (
                    <li key={l.sales_order_line_id} className="p-4">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="font-ui text-md font-semibold text-content">{l.product_name}</span>
                        <span className="flex items-center gap-3 text-sm">
                          <span className="text-content-muted">
                            requested <Qty value={l.quantity_requested} className="font-medium text-content" />
                          </span>
                          <span className="text-content-muted">
                            allocated{" "}
                            <Qty
                              value={l.quantity_allocated}
                              className="font-medium"
                              // colour only when it differs from what was asked for
                            />
                          </span>
                          {backordered ? (
                            <span style={{ color: BACKORDER_COLOR }}>
                              backordered <Qty value={l.quantity_backordered} className="font-semibold" />
                            </span>
                          ) : null}
                        </span>
                      </div>

                      <SplitBar className="mt-2.5" segments={segments} height={10} />

                      {l.explanation ? (
                        <p className="mt-2 text-sm leading-[19px] text-content-secondary">{l.explanation}</p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>

          {/* -- lines ------------------------------------------------------ */}
          <Panel>
            <PanelHead title="Order lines" subtitle={`${(o.lines ?? []).length} lines`} />
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-line bg-surface-sunken">
                    {["Product", "Qty", "Allocated", "Fulfilled", "Unit", "Amount"].map((h, i) => (
                      <th key={h} className={cn("h-8 px-3 font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint", i > 0 && "text-right")}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(o.lines ?? []).map((l) => (
                    <tr key={l.id} className="border-b border-line/60">
                      <td className="px-3 py-2">
                        <div className="font-medium text-content">{l.description}</div>
                        <div className="text-2xs uppercase tracking-wide text-content-faint">
                          {l.category}
                          {l.billing_type === "RECURRING" ? ` \u00b7 ${l.recurring_interval}` : ""}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right"><Qty value={l.quantity} /></td>
                      <td className="px-3 py-2 text-right"><Qty value={l.quantity_allocated} /></td>
                      <td className="px-3 py-2 text-right"><Qty value={l.quantity_fulfilled} /></td>
                      <td className="px-3 py-2 text-right"><Money value={l.unit_net_price} currency={o.currency} /></td>
                      <td className="px-3 py-2 text-right"><Money value={l.total_amount} currency={o.currency} className="font-semibold" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* -- shipments -------------------------------------------------- */}
          {(o.fulfillments?.length ?? 0) > 0 ? (
            <Panel>
              <PanelHead icon={<Truck className="size-4" />} title="Shipments" subtitle="One per warehouse" />
              <ul className="divide-y divide-line/70">
                {o.fulfillments!.map((f) => (
                  <li key={f.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-ui text-sm font-semibold text-content">
                        {f.warehouse_name ?? `Shipment ${f.shipment_sequence}`}
                      </p>
                      <p className="text-xs text-content-muted">
                        {f.fulfillment_number ? `${f.fulfillment_number} \u00b7 ` : ""}
                        {f.status.toLowerCase()}
                        {f.shipped_at ? ` \u00b7 shipped ${formatDate(f.shipped_at)}` : ""}
                      </p>
                    </div>
                    {can.fulfill && f.status === "SHIPPED" ? (
                      <Button
                        size="xs"
                        icon={<PackageCheck className="size-3" />}
                        loading={m.deliver.isPending}
                        onClick={() =>
                          m.deliver.mutate(f.id, {
                            onSuccess: () => toast.success("Marked delivered"),
                            onError: toast.fromError,
                          })
                        }
                      >
                        Confirm delivery
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </div>

        {/* -- rail --------------------------------------------------------- */}
        <div className="min-w-0 space-y-3">
          <Panel>
            <PanelHead dense title="Commercials" />
            <div className="px-3.5 py-1">
              <FieldList>
                <Field label="Gross"><Money value={o.gross_revenue} currency={o.currency} /></Field>
                <Field label="Discount"><Money value={o.total_discount} currency={o.currency} /></Field>
                <Field label="Subtotal"><Money value={o.subtotal} currency={o.currency} /></Field>
                <Field label="Tax"><Money value={o.tax_amount} currency={o.currency} /></Field>
                <Field label="Total"><Money value={o.total_amount} currency={o.currency} className="font-semibold" /></Field>
                <Field label="Cost"><Money value={o.total_cost} currency={o.currency} /></Field>
                <Field label="Margin">
                  <span className="flex items-baseline gap-2">
                    <Money value={o.margin} currency={o.currency} />
                    <Percent value={o.margin_pct} dp={1} className="text-xs text-content-muted" />
                  </span>
                </Field>
              </FieldList>
            </div>
          </Panel>

          <Panel>
            <PanelHead dense title="Billing" />
            <div className="p-3.5">
              {billing.isPending ? (
                <Skeleton className="h-16 w-full" />
              ) : billing.data ? (
                <>
                  <SplitBar
                    height={10}
                    segments={[
                      {
                        id: "one",
                        label: "One-time",
                        value: dec(billing.data.one_time_total).toNumber(),
                        color: "var(--accent-500)",
                        caption: `${billing.data.one_time_count}`,
                      },
                      {
                        id: "rec",
                        label: "Recurring",
                        value: dec(billing.data.recurring_contract_total).toNumber(),
                        color: "var(--state-negotiating)",
                        caption: `${billing.data.recurring_count}`,
                      },
                    ]}
                  />
                  <FieldList className="mt-3">
                    <Field label="One-time"><Money value={billing.data.one_time_total} currency={o.currency} /></Field>
                    <Field label="Recurring / yr"><Money value={billing.data.recurring_total_per_year} currency={o.currency} /></Field>
                    <Field label="Grand total"><Money value={billing.data.grand_total} currency={o.currency} className="font-semibold" /></Field>
                    <Field label="Schedules">{billing.data.schedule_count}</Field>
                  </FieldList>
                </>
              ) : (
                <p className="text-sm text-content-muted">No billing schedules yet.</p>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead dense title="Details" />
            <div className="px-3.5 py-1">
              <FieldList>
                <Field label="Quotation">
                  <Link to={`/quotes/${o.quote_id}`} className="text-accent-600 hover:underline">Open</Link>
                </Field>
                <Field label="Payment terms">{o.payment_terms?.replace(/_/g, " ")}</Field>
                <Field label="Confirmed">{formatDateTime(o.confirmed_at)}</Field>
                <Field label="Allocated">{o.allocated_at ? formatDateTime(o.allocated_at) : "\u2014"}</Field>
                <Field label="Fulfilled">{o.fulfilled_at ? formatDateTime(o.fulfilled_at) : "\u2014"}</Field>
                <Field label="Promised">
                  {o.promised_delivery_date ? (
                    <span className={o.is_delivery_late ? "text-[var(--risk-critical)]" : undefined}>
                      {formatDate(o.promised_delivery_date)}
                      {o.is_delivery_late ? ` (${o.days_late}d late)` : ""}
                    </span>
                  ) : (
                    "\u2014"
                  )}
                </Field>
              </FieldList>
            </div>
          </Panel>
        </div>
      </div>

      {/* -- promise dialog -------------------------------------------------- */}
      <Dialog
        open={promising}
        onOpenChange={setPromising}
        title="Promised delivery date"
        description="Slippage against this date raises a delivery signal on the Command Center."
        width="sm"
        footer={
          <>
            <Button onClick={() => setPromising(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!promiseDate}
              loading={m.promise.isPending}
              onClick={() =>
                m.promise.mutate(promiseDate, {
                  onSuccess: () => { setPromising(false); toast.success("Promise date set"); },
                  onError: toast.fromError,
                })
              }
            >
              Save
            </Button>
          </>
        }
      >
        <SectionLabel>Date</SectionLabel>
        <Input type="date" value={promiseDate} onChange={(e) => setPromiseDate(e.target.value)} aria-label="Promised delivery date" />
      </Dialog>

      {/* -- cancel dialog --------------------------------------------------- */}
      <Dialog
        open={cancelling}
        onOpenChange={setCancelling}
        title="Cancel this order"
        description="Reserved stock is released back to the warehouses it came from."
        width="sm"
        footer={
          <>
            <Button onClick={() => setCancelling(false)}>Keep order</Button>
            <Button
              variant="danger"
              loading={m.cancel.isPending}
              onClick={() =>
                m.cancel.mutate({}, {
                  onSuccess: () => { setCancelling(false); toast.info("Order cancelled, stock released"); },
                  onError: toast.fromError,
                })
              }
            >
              Cancel order
            </Button>
          </>
        }
      >
        <Tooltip content="Allocations return to available stock">
          <p className="text-sm text-content-secondary">
            This cannot be undone from the interface.
          </p>
        </Tooltip>
      </Dialog>
    </Page>
  );
}
