import { AlertTriangle, FileText, Plus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuotes } from "@/api/queries";
import type { QuoteListItem } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Button, CellStack, type Column, DataTable, EmptyState, Money, Panel,
  Percent, RiskBadge, SearchInput, Segmented, Select, TierBadge, Tooltip, VERSION_STATUS,
  VersionStatusBadge,
} from "@/design-system";
import { NewQuoteDialog } from "./NewQuoteDialog";
import { formatRelative, sortKey } from "@/api/money";

const STATUS_OPTIONS = [
  { value: "", label: "Any status" },
  ...Object.entries(VERSION_STATUS).map(([value, t]) => ({ value, label: t.label })),
];

/**
 * Margin is the one figure that changes colour on a threshold rather than a
 * state, so it gets its own cell. Bands mirror the seeded MIN_MARGIN policy
 * (10%) with a comfort zone above it.
 */
function MarginCell({ value }: { value: string | null | undefined }) {
  const v = Number(value ?? 0);
  const color =
    v >= 25 ? "var(--margin-healthy)" : v >= 12 ? "var(--margin-thin)" : "var(--margin-breach)";
  return <Percent value={value} dp={1} className="font-semibold" style={{ color }} />;
}

export function QuotesPage() {
  const nav = useNavigate();
  const can = useCan();
  const [search, setSearch] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [risk, setRisk] = React.useState<"all" | "attention">("all");
  const [creating, setCreating] = React.useState(false);
  const deferred = React.useDeferredValue(search);

  const query = useQuotes({ limit: 100, ...(status ? { version_status: status } : {}) });

  const filtered = React.useMemo(() => {
    const items = query.data?.items ?? [];
    const term = deferred.trim().toLowerCase();
    return items.filter((q) => {
      if (risk === "attention" && !q.is_stale && !q.requires_approval) return false;
      if (!term) return true;
      return (
        q.quote_number.toLowerCase().includes(term) ||
        (q.title ?? "").toLowerCase().includes(term) ||
        (q.customer_display_name ?? "").toLowerCase().includes(term) ||
        (q.owner_name ?? "").toLowerCase().includes(term)
      );
    });
  }, [query.data, deferred, risk]);

  const columns: Column<QuoteListItem>[] = [
    {
      id: "quote",
      header: "Quotation",
      width: "22%",
      sortValue: (q) => q.quote_number,
      cell: (q) => (
        <div className="flex items-center gap-2">
          <CellStack
            top={
              <span className="flex items-center gap-1.5">
                <span className="num">{q.quote_number}</span>
                <span className="text-xs font-normal text-content-faint">v{q.current_version_number}</span>
              </span>
            }
            bottom={q.title}
          />
          {q.is_stale ? (
            <Tooltip content="Approval invalidated by a change after approval. Confirmation is blocked.">
              <span className="shrink-0">
                <AlertTriangle aria-label="Stale approval" className="size-3.5 text-[var(--risk-critical)]" />
              </span>
            </Tooltip>
          ) : null}
        </div>
      ),
    },
    {
      id: "customer",
      header: "Customer",
      sortValue: (q) => q.customer_display_name ?? "",
      cell: (q) => (
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate">{q.customer_display_name}</span>
          {q.customer_tier ? <TierBadge tier={q.customer_tier} /> : null}
        </div>
      ),
      hideBelow: "md",
    },
    {
      id: "status",
      header: "State",
      sortValue: (q) => q.current_version_status ?? "",
      cell: (q) => (q.current_version_status ? <VersionStatusBadge value={q.current_version_status} size="sm" /> : <span className="text-content-faint">—</span>),
    },
    {
      id: "value",
      header: "Net revenue",
      align: "right",
      sortValue: (q) => sortKey(q.net_revenue ?? 0),
      cell: (q) => <Money value={q.net_revenue} className="font-semibold" />,
    },
    {
      id: "discount",
      header: "Disc.",
      align: "right",
      sortValue: (q) => sortKey(q.effective_discount_pct ?? 0),
      cell: (q) => <Percent value={q.effective_discount_pct} dp={1} className="text-content-secondary" />,
      hideBelow: "lg",
    },
    {
      id: "margin",
      header: "Margin",
      align: "right",
      sortValue: (q) => sortKey(q.margin_pct ?? 0),
      cell: (q) => <MarginCell value={q.margin_pct} />,
    },
    {
      id: "risk",
      header: "Risk",
      align: "right",
      sortValue: (q) => sortKey(q.blended_risk_score ?? 0),
      cell: (q) =>
        q.risk_band ? (
          <div className="flex items-center justify-end gap-1.5">
            <span className="num text-xs text-content-muted">{Number(q.blended_risk_score ?? 0).toFixed(1)}</span>
            <RiskBadge value={q.risk_band} size="sm" dot={false} />
          </div>
        ) : (
          <span className="text-content-faint">—</span>
        ),
      hideBelow: "sm",
    },
    {
      id: "owner",
      header: "Owner",
      sortValue: (q) => q.owner_name ?? "",
      cell: (q) => <span className="truncate text-content-secondary">{q.owner_name}</span>,
      hideBelow: "xl",
    },
    {
      id: "activity",
      header: "Activity",
      align: "right",
      sortValue: (q) => q.last_activity_at ?? "",
      cell: (q) => <span className="whitespace-nowrap text-xs text-content-muted">{formatRelative(q.last_activity_at)}</span>,
      hideBelow: "lg",
    },
  ];

  const needingAttention = (query.data?.items ?? []).filter((q) => q.is_stale || q.requires_approval).length;

  return (
    <Page
      title="Quotations"
      subtitle="Every quotation in the workspace, with the numbers the engine computed for each."
      actions={
        can.authorQuotes ? (
          <Button variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setCreating(true)}>
            New quotation
          </Button>
        ) : null
      }
    >
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput
            value={search}
            onValueChange={setSearch}
            placeholder="Search number, title, customer or owner"
            className="w-full max-w-xs"
          />
          <Select
            value={status}
            onValueChange={setStatus}
            options={STATUS_OPTIONS}
            placeholder="Any status"
            ariaLabel="Filter by version status"
            className="w-44"
            size="sm"
          />
          <Segmented
            ariaLabel="Filter by attention"
            value={risk}
            onValueChange={setRisk}
            options={[
              { value: "all", label: "All", count: query.data?.items.length },
              { value: "attention", label: "Needs attention", count: needingAttention },
            ]}
          />
          <span className="ml-auto text-xs text-content-muted">
            {filtered.length} of {query.data?.total ?? 0}
          </span>
        </div>

        <Async
          query={query}
          isEmpty={() => filtered.length === 0}
          empty={
            <EmptyState
              icon={<FileText className="size-5" />}
              title={search || status ? "No quotations match those filters" : "No quotations yet"}
              body={
                search || status
                  ? "Clear the filters to see everything in the workspace."
                  : "Create the first quotation to start the commercial workflow."
              }
              action={
                search || status ? (
                  <Button size="sm" onClick={() => { setSearch(""); setStatus(""); setRisk("all"); }}>
                    Clear filters
                  </Button>
                ) : can.authorQuotes ? (
                  <Button size="sm" variant="primary" onClick={() => setCreating(true)}>New quotation</Button>
                ) : null
              }
            />
          }
        >
          {() => (
            <DataTable
              rows={filtered}
              columns={columns}
              getKey={(q) => q.quote_id}
              caption="Quotations"
              onRowClick={(q) => nav(`/quotes/${q.quote_id}`)}
              rail={(q) =>
                q.is_stale
                  ? "var(--risk-critical)"
                  : q.current_version_status
                    ? VERSION_STATUS[q.current_version_status].fg
                    : undefined
              }
            />
          )}
        </Async>
      </Panel>

      {creating ? <NewQuoteDialog open onOpenChange={setCreating} /> : null}
    </Page>
  );
}

