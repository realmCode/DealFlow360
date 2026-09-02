import { Warehouse } from "lucide-react";
import * as React from "react";
import { dec, sortKey } from "@/api/money";
import { useAdminMutations, useInventory, useWarehouses } from "@/api/queries";
import type { WarehouseRead } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, Button, type Column, DataTable, Dialog, EmptyState, FormField, GovNote,
  Input, Money, NumericInput, Panel, Qty, toast,
} from "@/design-system";

export function WarehousesPage() {
  const can = useCan();
  const query = useWarehouses();
  const inventory = useInventory();
  const { createWarehouse, updateWarehouse } = useAdminMutations();
  const [editing, setEditing] = React.useState<WarehouseRead | "new" | null>(null);

  const stockByWarehouse = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const i of inventory.data ?? []) {
      map.set(i.warehouse_id, (map.get(i.warehouse_id) ?? 0) + dec(i.quantity_available).toNumber());
    }
    return map;
  }, [inventory.data]);

  const columns: Column<WarehouseRead>[] = [
    {
      id: "code",
      header: "Warehouse",
      sortValue: (w) => w.code,
      cell: (w) => (
        <div>
          <div className="font-medium text-content">{w.name}</div>
          <div className="num text-2xs text-content-faint">{w.code}</div>
        </div>
      ),
    },
    { id: "region", header: "Location", cell: (w) => [w.city, w.region, w.country].filter(Boolean).join(", ") || "\u2014", hideBelow: "md" },
    {
      id: "priority",
      header: "Priority",
      align: "right",
      sortValue: (w) => w.priority,
      cell: (w) => <span className="num font-semibold">{w.priority}</span>,
    },
    {
      id: "shipping",
      header: "Cost / shipment",
      align: "right",
      sortValue: (w) => sortKey(w.shipping_cost_per_shipment),
      cell: (w) => <Money value={w.shipping_cost_per_shipment} />,
    },
    {
      id: "stock",
      header: "Available units",
      align: "right",
      sortValue: (w) => stockByWarehouse.get(w.id) ?? 0,
      cell: (w) => <Qty value={String(stockByWarehouse.get(w.id) ?? 0)} />,
      hideBelow: "sm",
    },
    {
      id: "active",
      header: "State",
      cell: (w) =>
        w.is_active ? (
          <Badge size="sm" tone={{ fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Active" }} />
        ) : (
          <Badge size="sm" tone={{ fg: "var(--ink-500)", bg: "var(--ink-100)", label: "Inactive" }} />
        ),
    },
    ...(can.administer
      ? [{
          id: "edit",
          header: "",
          align: "right" as const,
          cell: (w: WarehouseRead) => (
            <Button size="xs" variant="ghost" onClick={(e) => { e.stopPropagation(); setEditing(w); }}>
              Edit
            </Button>
          ),
        }]
      : []),
  ];

  return (
    <Page
      title="Warehouses"
      subtitle="Priority and shipping cost are what produce the allocation split on every order."
      actions={can.administer ? <Button variant="primary" onClick={() => setEditing("new")}>New warehouse</Button> : null}
    >
      <GovNote className="mb-3" title="How the split is decided">
        When an order is allocated the engine walks warehouses in priority order, taking what each can supply
        before moving on. Anything still short becomes a backorder that consolidates automatically on the next
        stock receipt.
      </GovNote>

      <Panel>
        <Async
          query={query}
          isEmpty={(d) => d.length === 0}
          empty={<EmptyState icon={<Warehouse className="size-5" />} title="No warehouses" body="Add a warehouse before allocating any order." />}
        >
          {(items) => <DataTable rows={items} columns={columns} caption="Warehouses" getKey={(w) => w.id} />}
        </Async>
      </Panel>

      {editing ? (
        <WarehouseDialog
          warehouse={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSave={(body, id) =>
            id
              ? updateWarehouse.mutate({ id, body }, {
                  onSuccess: () => { toast.success("Warehouse updated"); setEditing(null); },
                  onError: toast.fromError,
                })
              : createWarehouse.mutate(body as never, {
                  onSuccess: () => { toast.success("Warehouse created"); setEditing(null); },
                  onError: toast.fromError,
                })
          }
          saving={createWarehouse.isPending || updateWarehouse.isPending}
        />
      ) : null}
    </Page>
  );
}

function WarehouseDialog({
  warehouse, onClose, onSave, saving,
}: {
  warehouse: WarehouseRead | null;
  onClose: () => void;
  onSave: (body: Record<string, unknown>, id?: string) => void;
  saving: boolean;
}) {
  const [code, setCode] = React.useState(warehouse?.code ?? "");
  const [name, setName] = React.useState(warehouse?.name ?? "");
  const [city, setCity] = React.useState(warehouse?.city ?? "");
  const [region, setRegion] = React.useState(warehouse?.region ?? "");
  const [country, setCountry] = React.useState(warehouse?.country ?? "");
  const [priority, setPriority] = React.useState(String(warehouse?.priority ?? 10));
  const [cost, setCost] = React.useState(dec(warehouse?.shipping_cost_per_shipment ?? "0").toString());

  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      title={warehouse ? `Edit ${warehouse.name}` : "New warehouse"}
      description="Lower priority numbers are drawn from first."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={saving}
            disabled={!name.trim() || (!warehouse && !code.trim())}
            onClick={() =>
              onSave(
                warehouse
                  ? { name, city, region, country, priority: Number(priority), shipping_cost_per_shipment: cost }
                  : { code, name, city, region, country, priority: Number(priority), shipping_cost_per_shipment: cost },
                warehouse?.id,
              )
            }
          >
            {warehouse ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {!warehouse ? (
          <FormField label="Code" required>
            {(p) => <Input {...p} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="MAIN" />}
          </FormField>
        ) : null}
        <FormField label="Name" required>{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}</FormField>
        <div className="grid grid-cols-3 gap-2">
          <FormField label="City">{(p) => <Input {...p} value={city} onChange={(e) => setCity(e.target.value)} />}</FormField>
          <FormField label="Region">{(p) => <Input {...p} value={region} onChange={(e) => setRegion(e.target.value)} />}</FormField>
          <FormField label="Country">{(p) => <Input {...p} value={country} onChange={(e) => setCountry(e.target.value)} />}</FormField>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <FormField label="Priority" hint="Lower is drawn first">
            {(p) => <NumericInput id={p.id} value={priority} onValueChange={setPriority} />}
          </FormField>
          <FormField label="Shipping cost per shipment">
            {(p) => <NumericInput id={p.id} value={cost} onValueChange={setCost} />}
          </FormField>
        </div>
      </div>
    </Dialog>
  );
}
