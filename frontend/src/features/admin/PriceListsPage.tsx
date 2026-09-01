import { Layers, Tags } from "lucide-react";
import { usePriceLists, useVariants } from "@/api/queries";
import type { PriceListRead, ProductVariantRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, type Column, DataTable, EmptyState, Money, Panel, PanelHead, TierBadge,
} from "@/design-system";

/**
 * Price lists and variants are real endpoints that seed empty. Rather than
 * inventing rows, this ships a genuine empty state that explains what the
 * feature does and what fills it.
 */
export function PriceListsPage() {
  const priceLists = usePriceLists();
  const variants = useVariants();

  const priceColumns: Column<PriceListRead>[] = [
    { id: "name", header: "Price list", sortValue: (p) => p.name ?? "", cell: (p) => <span className="font-medium text-content">{p.name}</span> },
    { id: "tier", header: "Tier", cell: (p) => (p.tier ? <TierBadge tier={p.tier} /> : <span className="text-xs text-content-faint">any</span>) },
    { id: "currency", header: "Currency", cell: (p) => p.currency },
    {
      id: "rule",
      header: "Rule",
      align: "right",
      cell: (p) =>
        (p.rules?.length ?? 0) > 0 ? (
          <span className="num">{p.rules.length} rule{p.rules.length === 1 ? "" : "s"}</span>
        ) : (
          <span className="text-content-muted">List price, no adjustment</span>
        ),
    },
    {
      id: "active",
      header: "State",
      cell: (p) => (p.is_active ? <Badge size="sm" tone={{ fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Active" }} /> : <Badge size="sm" tone={{ fg: "var(--ink-500)", bg: "var(--ink-100)", label: "Off" }} />),
    },
  ];

  const variantColumns: Column<ProductVariantRead>[] = [
    { id: "sku", header: "Variant", sortValue: (v) => v.sku ?? "", cell: (v) => <span className="num font-medium text-content">{v.sku}</span> },
    { id: "name", header: "Name", cell: (v) => v.name },
    {
      id: "attributes",
      header: "Attributes",
      cell: (v) => {
        const pairs = Object.entries(v.attributes ?? {});
        return pairs.length ? (
          <span className="flex flex-wrap gap-1">
            {pairs.map(([k, val]) => (
              <span key={k} className="rounded-sm border border-line px-1.5 py-0.5 text-2xs text-content-muted">
                {k}: {String(val)}
              </span>
            ))}
          </span>
        ) : (
          <span className="text-content-faint">\u2014</span>
        );
      },
    },
    { id: "delta", header: "Extra price", align: "right", cell: (v) => <Money value={v.price_delta ?? "0"} signed className="font-semibold" /> },
  ];

  return (
    <Page title="Price lists and variants" subtitle="Tier pricing rules and per-attribute product variations.">
      <div className="space-y-3">
        <Panel>
          <PanelHead icon={<Tags className="size-4" />} title="Tier price lists" subtitle="Applied on top of the catalogue list price" />
          <Async
            query={priceLists}
            isEmpty={(d) => d.length === 0}
            empty={
              <EmptyState
                icon={<Tags className="size-5" />}
                title="No price lists configured"
                body="A price list applies a standing adjustment for a customer tier — for example Gold buying at list minus 10%. Without one, every quotation starts from the catalogue list price and discounts are applied per line."
              />
            }
          >
            {(rows) => <DataTable rows={rows} columns={priceColumns} caption="Price lists" getKey={(p) => p.id} />}
          </Async>
        </Panel>

        <Panel>
          <PanelHead icon={<Layers className="size-4" />} title="Product variants" subtitle="Attribute options that adjust the unit price" />
          <Async
            query={variants}
            isEmpty={(d) => d.length === 0}
            empty={
              <EmptyState
                icon={<Layers className="size-5" />}
                title="No variants configured"
                body="Variants let one catalogue product carry options — memory, colour, manufacturer — each with its own price delta. Products without variants quote at their base price."
              />
            }
          >
            {(rows) => <DataTable rows={rows} columns={variantColumns} caption="Product variants" getKey={(v) => v.id} />}
          </Async>
        </Panel>
      </div>
    </Page>
  );
}
