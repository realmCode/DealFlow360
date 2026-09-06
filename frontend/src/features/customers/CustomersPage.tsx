import { Building2 } from "lucide-react";
import * as React from "react";
import { useCustomers } from "@/api/queries";
import type { CustomerProfileRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, type Column, DataTable, EmptyState, Money, Panel, Percent, SearchInput,
  SplitBar, TierBadge,
} from "@/design-system";
import { dec, sortKey } from "@/api/money";

export function CustomersPage() {
  const query = useCustomers();
  const [search, setSearch] = React.useState("");

  const rows = React.useMemo(() => {
    const items = query.data ?? [];
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((c) => c.display_name.toLowerCase().includes(term) || c.tier.toLowerCase().includes(term));
  }, [query.data, search]);

  const columns: Column<CustomerProfileRead>[] = [
    {
      id: "name",
      header: "Customer",
      sortValue: (c) => c.display_name,
      cell: (c) => (
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium text-content">{c.display_name}</span>
          <TierBadge tier={c.tier} />
        </div>
      ),
    },
    { id: "terms", header: "Payment terms", sortValue: (c) => c.payment_terms, cell: (c) => c.payment_terms.replace(/_/g, " ") },
    { id: "currency", header: "Currency", cell: (c) => c.currency, hideBelow: "md" },
    { id: "limit", header: "Credit limit", align: "right", sortValue: (c) => sortKey(c.credit_limit), cell: (c) => <Money value={c.credit_limit} currency={c.currency} /> },
    { id: "used", header: "Used", align: "right", sortValue: (c) => sortKey(c.credit_used), cell: (c) => <Money value={c.credit_used} currency={c.currency} className="text-content-muted" />, hideBelow: "sm" },
    {
      id: "headroom",
      header: "Credit headroom",
      width: "200px",
      cell: (c) => (
        <SplitBar
          showLegend={false}
          height={6}
          segments={[
            { id: "u", label: "Used", value: dec(c.credit_used).toNumber(), color: "var(--gov-500)" },
            { id: "a", label: "Available", value: dec(c.credit_available).toNumber(), color: "var(--policy-passed)" },
          ]}
        />
      ),
      hideBelow: "lg",
    },
    { id: "available", header: "Available", align: "right", sortValue: (c) => sortKey(c.credit_available), cell: (c) => <Money value={c.credit_available} currency={c.currency} className="font-semibold" /> },
    { id: "tax", header: "Tax", align: "right", cell: (c) => <Percent value={c.tax_rate_pct} dp={2} className="text-content-muted" />, hideBelow: "xl" },
    {
      id: "active",
      header: "State",
      cell: (c) =>
        c.is_active ? (
          <Badge size="sm" tone={{ fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Active" }} />
        ) : (
          <Badge size="sm" tone={{ fg: "var(--ink-500)", bg: "var(--ink-100)", label: "Inactive" }} />
        ),
    },
  ];

  return (
    <Page
      title="Customers"
      subtitle="Tier and payment terms decide which discount ceilings apply to every quotation."
    >
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput value={search} onValueChange={setSearch} placeholder="Search name or tier" className="w-full max-w-xs" />
          <span className="ml-auto text-xs text-content-muted">{rows.length} customers</span>
        </div>
        <Async
          query={query}
          isEmpty={() => rows.length === 0}
          empty={<EmptyState icon={<Building2 className="size-5" />} title="No customers" body="Customers are created alongside their buying organisation." />}
        >
          {() => <DataTable rows={rows} columns={columns} caption="Customers" getKey={(c) => c.id} />}
        </Async>
      </Panel>
    </Page>
  );
}
