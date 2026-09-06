import { Package, Plus } from "lucide-react";
import * as React from "react";
import { dec, sortKey } from "@/api/money";
import { useAdminMutations, useProducts } from "@/api/queries";
import type { ProductCategory, ProductRead, RecurringInterval } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, Button, Checkbox, type Column, DataTable, Dialog, EmptyState, FormField,
  GovNote, Input, Money, NumericInput, Panel, Percent, SearchInput, Select, Textarea, toast,
} from "@/design-system";

const CATEGORIES: ProductCategory[] = ["HARDWARE", "SOFTWARE", "SERVICE", "SUBSCRIPTION"];
/* The wireframe offers Monthly/Yearly/Weekly. The backend enum is
   MONTHLY | QUARTERLY | YEARLY, so those are the three offered. */
const INTERVALS: RecurringInterval[] = ["MONTHLY", "QUARTERLY", "YEARLY"];

const CATEGORY_TONE: Record<string, { fg: string; bg: string; label: string }> = {
  HARDWARE: { fg: "var(--accent-600)", bg: "var(--accent-100)", label: "Hardware" },
  SOFTWARE: { fg: "var(--state-negotiating)", bg: "var(--state-negotiating-bg)", label: "Software" },
  SERVICE: { fg: "var(--gov-600)", bg: "var(--gov-100)", label: "Service" },
  SUBSCRIPTION: { fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Subscription" },
};

export function ProductsPage() {
  const can = useCan();
  const query = useProducts({ limit: 200 });
  const { createProduct, updateProduct } = useAdminMutations();
  const [search, setSearch] = React.useState("");
  const [editing, setEditing] = React.useState<ProductRead | "new" | null>(null);

  const items = query.data?.items;
  const rows = React.useMemo(() => {
    const all = items ?? [];
    const term = search.trim().toLowerCase();
    if (!term) return all;
    return all.filter((p) => p.name.toLowerCase().includes(term) || p.sku.toLowerCase().includes(term));
  }, [items, search]);

  const columns: Column<ProductRead>[] = [
    {
      id: "product",
      header: "Product",
      sortValue: (p) => p.name,
      cell: (p) => (
        <div>
          <div className="font-medium text-content">{p.name}</div>
          <div className="num text-2xs text-content-faint">{p.sku}</div>
        </div>
      ),
    },
    { id: "category", header: "Category", sortValue: (p) => p.category, cell: (p) => <Badge size="sm" tone={CATEGORY_TONE[p.category]} /> },
    {
      id: "billing",
      header: "Billing",
      cell: (p) =>
        p.billing_type === "RECURRING" ? (
          <span className="text-xs text-content-secondary">
            Recurring &middot; {p.recurring_interval?.toLowerCase()}
            {p.default_recurring_periods > 1 ? ` \u00d7${p.default_recurring_periods}` : ""}
          </span>
        ) : (
          <span className="text-xs text-content-muted">One-time</span>
        ),
      hideBelow: "md",
    },
    { id: "price", header: "List price", align: "right", sortValue: (p) => sortKey(p.list_price), cell: (p) => <Money value={p.list_price} dp={2} className="font-semibold" /> },
    { id: "cost", header: "Cost", align: "right", sortValue: (p) => sortKey(p.internal_cost), cell: (p) => <Money value={p.internal_cost} dp={2} className="text-content-muted" />, hideBelow: "sm" },
    {
      id: "margin",
      header: "Margin",
      align: "right",
      sortValue: (p) => {
        const lp = dec(p.list_price);
        return lp.isZero() ? 0 : lp.minus(dec(p.internal_cost)).div(lp).times(100).toNumber();
      },
      cell: (p) => {
        const lp = dec(p.list_price);
        const pct = lp.isZero() ? "0" : lp.minus(dec(p.internal_cost)).div(lp).times(100).toString();
        return <Percent value={pct} dp={1} />;
      },
    },
    { id: "uom", header: "Unit", cell: (p) => <span className="text-xs text-content-muted">{p.uom}</span>, hideBelow: "xl" },
    {
      id: "stock",
      header: "Tracked",
      align: "center",
      cell: (p) => (p.is_stock_tracked ? <span className="text-xs text-content-secondary">Yes</span> : <span className="text-xs text-content-faint">No</span>),
      hideBelow: "lg",
    },
    ...(can.administer
      ? [{
          id: "edit", header: "", align: "right" as const,
          cell: (p: ProductRead) => (
            <Button size="xs" variant="ghost" onClick={() => setEditing(p)}>Edit</Button>
          ),
        }]
      : []),
  ];

  return (
    <Page
      title="Product catalogue"
      subtitle="List price and internal cost drive every margin figure in the product."
      actions={can.administer ? <Button variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setEditing("new")}>New product</Button> : null}
    >
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput value={search} onValueChange={setSearch} placeholder="Search name or SKU" className="w-full max-w-xs" />
          <span className="ml-auto text-xs text-content-muted">{rows.length} products</span>
        </div>
        <Async
          query={query}
          isEmpty={() => rows.length === 0}
          empty={<EmptyState icon={<Package className="size-5" />} title="No products" body="Add a product before building a quotation." />}
        >
          {() => <DataTable rows={rows} columns={columns} caption="Products" getKey={(p) => p.id} rail={(p) => CATEGORY_TONE[p.category].fg} />}
        </Async>
      </Panel>

      {editing ? (
        <ProductDialog
          product={editing === "new" ? null : editing}
          saving={createProduct.isPending || updateProduct.isPending}
          onClose={() => setEditing(null)}
          onSave={(body, id) =>
            id
              ? updateProduct.mutate({ id, body }, { onSuccess: () => { toast.success("Product updated"); setEditing(null); }, onError: toast.fromError })
              : createProduct.mutate(body as never, { onSuccess: () => { toast.success("Product created"); setEditing(null); }, onError: toast.fromError })
          }
        />
      ) : null}
    </Page>
  );
}

function ProductDialog({
  product, onClose, onSave, saving,
}: {
  product: ProductRead | null;
  onClose: () => void;
  onSave: (body: Record<string, unknown>, id?: string) => void;
  saving: boolean;
}) {
  const [sku, setSku] = React.useState(product?.sku ?? "");
  const [name, setName] = React.useState(product?.name ?? "");
  const [description, setDescription] = React.useState(product?.description ?? "");
  const [category, setCategory] = React.useState<ProductCategory>(product?.category ?? "HARDWARE");
  const [listPrice, setListPrice] = React.useState(dec(product?.list_price ?? "0").toString());
  const [cost, setCost] = React.useState(dec(product?.internal_cost ?? "0").toString());
  const [tax, setTax] = React.useState(dec(product?.tax_rate_pct ?? "0").toString());
  const [uom, setUom] = React.useState(product?.uom ?? "EACH");
  const [recurring, setRecurring] = React.useState(product?.billing_type === "RECURRING");
  const [interval, setInterval] = React.useState<RecurringInterval>(product?.recurring_interval ?? "YEARLY");
  const [tracked, setTracked] = React.useState(product?.is_stock_tracked ?? true);

  const margin = dec(listPrice).isZero()
    ? "0"
    : dec(listPrice).minus(dec(cost)).div(dec(listPrice)).times(100).toString();

  const body = () => ({
    ...(product ? {} : { sku }),
    name, description: description || null, category,
    list_price: listPrice, internal_cost: cost, tax_rate_pct: tax, uom,
    billing_type: recurring ? "RECURRING" : "ONE_TIME",
    recurring_interval: recurring ? interval : null,
    is_stock_tracked: tracked,
  });

  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      title={product ? `Edit ${product.name}` : "New product"}
      width="lg"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={saving} disabled={!name.trim() || (!product && !sku.trim())} onClick={() => onSave(body(), product?.id)}>
            {product ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          {!product ? (
            <FormField label="SKU" required>{(p) => <Input {...p} value={sku} onChange={(e) => setSku(e.target.value.toUpperCase())} placeholder="HW-LAPTOP-01" />}</FormField>
          ) : null}
          <FormField label="Name" required>{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}</FormField>
          <FormField label="Category">
            {(p) => <Select id={p.id} value={category} onValueChange={(v) => setCategory(v as ProductCategory)} options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY_TONE[c].label }))} />}
          </FormField>
        </div>

        <FormField label="Description">{(p) => <Textarea {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</FormField>

        <div className="grid gap-3 sm:grid-cols-4">
          <FormField label="List price" required>{(p) => <NumericInput id={p.id} value={listPrice} onValueChange={setListPrice} />}</FormField>
          <FormField label="Internal cost" required>{(p) => <NumericInput id={p.id} value={cost} onValueChange={setCost} />}</FormField>
          <FormField label="Tax %">{(p) => <NumericInput id={p.id} value={tax} onValueChange={setTax} suffix="%" />}</FormField>
          <FormField label="Unit">{(p) => <Input {...p} value={uom} onChange={(e) => setUom(e.target.value.toUpperCase())} />}</FormField>
        </div>

        <GovNote title="Margin at list price">
          <Percent value={margin} dp={2} className="font-semibold" /> — before any discount is applied.
        </GovNote>

        <div className="space-y-2 rounded-md border border-line p-3">
          <Checkbox checked={recurring} onCheckedChange={setRecurring} label="This is a subscription (recurring billing)" />
          {recurring ? (
            <FormField label="Interval" inline>
              {(p) => <Select id={p.id} className="w-40" value={interval} onValueChange={(v) => setInterval(v as RecurringInterval)} options={INTERVALS.map((i) => ({ value: i, label: i.charAt(0) + i.slice(1).toLowerCase() }))} />}
            </FormField>
          ) : null}
          <Checkbox checked={tracked} onCheckedChange={setTracked} label="Track stock for this product" />
        </div>
      </div>
    </Dialog>
  );
}
