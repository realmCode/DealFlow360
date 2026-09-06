import { PackageSearch } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { formatRelative, sortKey } from "@/api/money";
import { useOrders } from "@/api/queries";
import type { SalesOrderSummary } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, CellStack, type Column, DataTable, EmptyState, Money, ORDER_STATUS,
  OrderStatusBadge, Panel, Percent,
} from "@/design-system";

export function OrdersPage() {
  const nav = useNavigate();
  const query = useOrders({ limit: 100 });

  const columns: Column<SalesOrderSummary>[] = [
    {
      id: "order",
      header: "Order",
      sortValue: (o) => o.order_number,
      cell: (o) => <CellStack top={<span className="num">{o.order_number}</span>} bottom={o.customer_name} />,
    },
    { id: "status", header: "Status", sortValue: (o) => o.status, cell: (o) => <OrderStatusBadge value={o.status} size="sm" /> },
    {
      id: "flags",
      header: "Flags",
      cell: (o) => (
        <span className="flex flex-wrap gap-1">
          {o.has_backorder ? (
            <Badge size="sm" tone={{ fg: "var(--risk-high)", bg: "var(--risk-high-bg)", label: "Backorder" }} />
          ) : null}
          {!o.fully_allocated && !o.has_backorder ? (
            <Badge size="sm" tone={{ fg: "var(--state-pending)", bg: "var(--state-pending-bg)", label: "Unallocated" }} />
          ) : null}
          {o.is_delivery_late ? (
            <Badge size="sm" tone={{ fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: `${o.days_late}d late` }} />
          ) : null}
        </span>
      ),
      hideBelow: "md",
    },
    { id: "total", header: "Total", align: "right", sortValue: (o) => sortKey(o.total_amount), cell: (o) => <Money value={o.total_amount} currency={o.currency} className="font-semibold" /> },
    { id: "onetime", header: "One-time", align: "right", sortValue: (o) => sortKey(o.one_time_amount), cell: (o) => <Money value={o.one_time_amount} currency={o.currency} />, hideBelow: "lg" },
    { id: "recurring", header: "Recurring", align: "right", sortValue: (o) => sortKey(o.recurring_amount), cell: (o) => <Money value={o.recurring_amount} currency={o.currency} />, hideBelow: "lg" },
    { id: "margin", header: "Margin", align: "right", sortValue: (o) => sortKey(o.margin_pct), cell: (o) => <Percent value={o.margin_pct} dp={1} />, hideBelow: "sm" },
    { id: "confirmed", header: "Confirmed", align: "right", sortValue: (o) => o.confirmed_at ?? "", cell: (o) => <span className="whitespace-nowrap text-xs text-content-muted">{formatRelative(o.confirmed_at)}</span>, hideBelow: "xl" },
  ];

  return (
    <Page title="Orders" subtitle="Confirmed quotations, their allocation state and their fulfilment progress.">
      <Panel>
        <Async
          query={query}
          isEmpty={(d) => (d.items?.length ?? 0) === 0}
          empty={
            <EmptyState
              icon={<PackageSearch className="size-5" />}
              title="No orders yet"
              body="An order is created when a customer confirms an approved quotation."
            />
          }
        >
          {(page) => (
            <DataTable
              rows={page.items}
              columns={columns}
              caption="Sales orders"
              getKey={(o) => o.id}
              onRowClick={(o) => nav(`/orders/${o.id}`)}
              rail={(o) => (o.has_backorder ? "var(--risk-high)" : ORDER_STATUS[o.status].fg)}
            />
          )}
        </Async>
      </Panel>
    </Page>
  );
}
