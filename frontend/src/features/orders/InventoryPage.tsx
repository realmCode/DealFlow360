import { Boxes } from "lucide-react";
import * as React from "react";
import { dec, sortKey } from "@/api/money";
import { useInventory, useWarehouses } from "@/api/queries";
import type { InventoryRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, type Column, DataTable, EmptyState, Panel, Qty, SearchInput, Segmented, SplitBar,
} from "@/design-system";

export function InventoryPage() {
  const query = useInventory();
  const warehouses = useWarehouses();
  const [search, setSearch] = React.useState("");
  const [scope, setScope] = React.useState<"all" | "low">("all");

  const rows = React.useMemo(() => {
    const items = query.data ?? [];
    const term = search.trim().toLowerCase();
    return items.filter((i) => {
      if (scope === "low" && !dec(i.quantity_available).lte(dec(i.reorder_point))) return false;
      if (!term) return true;
      return (
        (i.product_name ?? "").toLowerCase().includes(term) ||
        (i.product_sku ?? "").toLowerCase().includes(term) ||
        (i.warehouse_name ?? "").toLowerCase().includes(term)
      );
    });
  }, [query.data, search, scope]);

  const lowCount = (query.data ?? []).filter((i) => dec(i.quantity_available).lte(dec(i.reorder_point))).length;

  const columns: Column<InventoryRead>[] = [
    {
      id: "product",
      header: "Product",
      sortValue: (i) => i.product_name ?? "",
      cell: (i) => (
        <div>
          <div className="font-medium text-content">{i.product_name}</div>
          <div className="num text-2xs text-content-faint">{i.product_sku}</div>
        </div>
      ),
    },
    { id: "warehouse", header: "Warehouse", sortValue: (i) => i.warehouse_name ?? "", cell: (i) => i.warehouse_name },
    { id: "onhand", header: "On hand", align: "right", sortValue: (i) => sortKey(i.quantity_on_hand), cell: (i) => <Qty value={i.quantity_on_hand} /> },
    {
      id: "reserved",
      header: "Reserved",
      align: "right",
      sortValue: (i) => sortKey(i.quantity_reserved),
      cell: (i) => <Qty value={i.quantity_reserved} className="text-content-muted" />,
    },
    {
      id: "available",
      header: "Available",
      align: "right",
      sortValue: (i) => sortKey(i.quantity_available),
      cell: (i) => {
        const low = dec(i.quantity_available).lte(dec(i.reorder_point));
        return (
          <Qty
            value={i.quantity_available}
            className="font-semibold"
            // low stock is the one thing worth colouring in this table
            {...(low ? { style: { color: "var(--risk-high)" } } : {})}
          />
        );
      },
    },
    {
      id: "mix",
      header: "Reserved vs available",
      width: "180px",
      cell: (i) => (
        <SplitBar
          showLegend={false}
          height={6}
          segments={[
            { id: "r", label: "Reserved", value: dec(i.quantity_reserved).toNumber(), color: "var(--gov-500)" },
            { id: "a", label: "Available", value: dec(i.quantity_available).toNumber(), color: "var(--policy-passed)" },
          ]}
        />
      ),
      hideBelow: "lg",
    },
    { id: "reorder", header: "Reorder at", align: "right", sortValue: (i) => sortKey(i.reorder_point), cell: (i) => <Qty value={i.reorder_point} className="text-content-muted" />, hideBelow: "xl" },
    { id: "inbound", header: "Inbound", align: "right", sortValue: (i) => sortKey(i.quantity_inbound), cell: (i) => <Qty value={i.quantity_inbound} className="text-content-muted" />, hideBelow: "xl" },
  ];

  return (
    <Page
      title="Inventory"
      subtitle={`Stock by warehouse and product. Available is on hand minus reserved.${warehouses.data ? ` ${warehouses.data.length} warehouses.` : ""}`}
    >
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput value={search} onValueChange={setSearch} placeholder="Search product or warehouse" className="w-full max-w-xs" />
          <Segmented
            ariaLabel="Stock filter"
            value={scope}
            onValueChange={setScope}
            options={[
              { value: "all", label: "All", count: query.data?.length },
              { value: "low", label: "At or below reorder", count: lowCount },
            ]}
          />
        </div>
        <Async
          query={query}
          isEmpty={() => rows.length === 0}
          empty={<EmptyState icon={<Boxes className="size-5" />} title="No stock records" body="Stock is set per warehouse and product from Administration." />}
        >
          {() => (
            <DataTable
              rows={rows}
              columns={columns}
              caption="Inventory"
              getKey={(i) => i.id}
              rail={(i) => (dec(i.quantity_available).lte(dec(i.reorder_point)) ? "var(--risk-high)" : undefined)}
            />
          )}
        </Async>
      </Panel>
    </Page>
  );
}
