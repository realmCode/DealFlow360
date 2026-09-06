import { Briefcase } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { formatRelative, sortKey } from "@/api/money";
import { useDeals } from "@/api/queries";
import type { DealRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, CellStack, type Column, DataTable, DEAL_STAGE, DealStageBadge, EmptyState,
  Money, Panel, SearchInput, TierBadge,
} from "@/design-system";
import { rows as unwrap } from "@/api/client";

export function DealsPage() {
  const query = useDeals({ limit: 100 });
  const [search, setSearch] = React.useState("");

  const all = unwrap(query.data as never) as DealRead[];
  const filtered = React.useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return all;
    return all.filter(
      (d) =>
        d.reference.toLowerCase().includes(term) ||
        d.name.toLowerCase().includes(term) ||
        (d.customer_display_name ?? "").toLowerCase().includes(term),
    );
  }, [all, search]);

  const columns: Column<DealRead>[] = [
    {
      id: "deal",
      header: "Deal",
      sortValue: (d) => d.reference,
      cell: (d) => <CellStack top={<span className="num">{d.reference}</span>} bottom={d.name} />,
    },
    {
      id: "customer",
      header: "Customer",
      sortValue: (d) => d.customer_display_name ?? "",
      cell: (d) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate">{d.customer_display_name}</span>
          {d.customer_tier ? <TierBadge tier={d.customer_tier} /> : null}
        </span>
      ),
    },
    { id: "stage", header: "Stage", sortValue: (d) => d.stage, cell: (d) => <DealStageBadge value={d.stage} size="sm" /> },
    {
      id: "value",
      header: "Expected value",
      align: "right",
      sortValue: (d) => sortKey(d.expected_value ?? 0),
      cell: (d) => <Money value={d.expected_value} currency={d.currency} className="font-semibold" />,
    },
    {
      id: "quotes",
      header: "Quotations",
      align: "right",
      sortValue: (d) => d.quotes?.length ?? 0,
      cell: (d) => (
        <span className="flex flex-wrap justify-end gap-1">
          {(d.quotes ?? []).slice(0, 3).map((q) => (
            <Link
              key={q.id}
              to={`/quotes/${q.id}`}
              className="num rounded-sm border border-line px-1.5 py-0.5 text-2xs text-accent-600 transition-colors hover:border-accent-400"
            >
              {q.quote_number}
            </Link>
          ))}
          {(d.quotes?.length ?? 0) > 3 ? (
            <Badge size="sm" tone={{ fg: "var(--ink-500)", bg: "var(--ink-100)", label: `+${d.quotes!.length - 3}` }} dot={false} />
          ) : null}
        </span>
      ),
      hideBelow: "md",
    },
    {
      id: "updated",
      header: "Updated",
      align: "right",
      sortValue: (d) => d.updated_at,
      cell: (d) => <span className="whitespace-nowrap text-xs text-content-muted">{formatRelative(d.updated_at)}</span>,
      hideBelow: "lg",
    },
  ];

  return (
    <Page title="Deals" subtitle="The pipeline objects quotations belong to.">
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput value={search} onValueChange={setSearch} placeholder="Search reference, name or customer" className="w-full max-w-xs" />
          <span className="ml-auto text-xs text-content-muted">{filtered.length} deals</span>
        </div>
        <Async
          query={query}
          isEmpty={() => filtered.length === 0}
          empty={<EmptyState icon={<Briefcase className="size-5" />} title="No deals" body="A deal is created with the first quotation for a customer." />}
        >
          {() => (
            <DataTable
              rows={filtered}
              columns={columns}
              caption="Deals"
              getKey={(d) => d.id}
              rail={(d) => DEAL_STAGE[d.stage].fg}
            />
          )}
        </Async>
      </Panel>
    </Page>
  );
}
