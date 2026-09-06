import { AlertTriangle, Plus } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { useQuotes } from "@/api/queries";
import { formatRelative } from "@/api/money";
import type { QuoteListItem, QuoteVersionStatus } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Button, EmptyState, Money, Percent, RiskBadge, Skeleton, TierBadge, Tooltip,
  VERSION_STATUS,
} from "@/design-system";
import { NewQuoteDialog } from "./NewQuoteDialog";

/**
 * The wireframe's Kanban has five columns. The backend has eight version
 * statuses; SENT is added here because it is the state a quote occupies while
 * the customer is deciding, and hiding it would lose the pipeline's waiting
 * stage. REJECTED and SUPERSEDED are terminal, so they stay out of the board.
 */
const COLUMNS: QuoteVersionStatus[] = [
  "DRAFT", "PENDING_APPROVAL", "APPROVED", "SENT", "NEGOTIATING", "CONFIRMED",
];

function Card({ quote }: { quote: QuoteListItem }) {
  return (
    <Link
      to={`/quotes/${quote.quote_id}`}
      className="group relative block overflow-hidden rounded-md border border-line bg-surface p-2.5 transition-all duration-fast hover:border-accent-400 hover:shadow-pop"
    >
      {quote.is_stale ? (
        <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: "var(--risk-critical)" }} />
      ) : null}
      <div className="flex items-center gap-1.5">
        <span className="num text-sm font-semibold text-content">{quote.quote_number}</span>
        <span className="text-2xs text-content-faint">v{quote.current_version_number}</span>
        {quote.is_stale ? (
          <Tooltip content="Approval invalidated — confirmation is blocked">
            <AlertTriangle className="size-3 shrink-0 text-[var(--risk-critical)]" />
          </Tooltip>
        ) : null}
      </div>

      <p className="mt-0.5 truncate text-sm text-content-secondary">{quote.customer_display_name}</p>

      <div className="mt-2 flex items-baseline justify-between gap-2">
        <Money value={quote.net_revenue} className="text-md font-semibold" />
        {quote.customer_tier ? <TierBadge tier={quote.customer_tier} /> : null}
      </div>

      <div className="mt-2 flex items-center gap-2 border-t border-line/70 pt-2">
        <span className="micro">M</span>
        <Percent value={quote.margin_pct} dp={1} className="text-xs font-medium text-content-secondary" />
        {quote.risk_band ? <RiskBadge value={quote.risk_band} size="sm" dot={false} className="ml-auto" /> : null}
      </div>

      <p className="mt-1.5 text-2xs text-content-faint">{formatRelative(quote.last_activity_at)}</p>
    </Link>
  );
}

export function PipelinePage() {
  const can = useCan();
  const [creating, setCreating] = React.useState(false);
  const query = useQuotes({ limit: 200 });

  const byStatus = React.useMemo(() => {
    const map = new Map<QuoteVersionStatus, QuoteListItem[]>(COLUMNS.map((c) => [c, []]));
    for (const q of query.data?.items ?? []) {
      const bucket = q.current_version_status ? map.get(q.current_version_status) : undefined;
      if (bucket) bucket.push(q);
    }
    return map;
  }, [query.data]);

  return (
    <Page
      title="Pipeline"
      subtitle="Every open quotation by the state of its current version."
      wide
      actions={
        can.authorQuotes ? (
          <Button variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setCreating(true)}>
            New quotation
          </Button>
        ) : null
      }
    >
      <Async
        query={query}
        skeleton={
          <div className="grid gap-2 lg:grid-cols-3 2xl:grid-cols-6">
            {COLUMNS.map((c) => (
              <div key={c} className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
            ))}
          </div>
        }
        isEmpty={(d) => d.items.length === 0}
        empty={<EmptyState title="No quotations yet" body="The board fills as quotations move through the workflow." />}
      >
        {() => (
          <div className="grid gap-2 lg:grid-cols-3 2xl:grid-cols-6">
            {COLUMNS.map((status) => {
              const items = byStatus.get(status) ?? [];
              const tone = VERSION_STATUS[status];
              const total = items.reduce((sum, q) => sum + Number(q.net_revenue ?? 0), 0);
              return (
                <section key={status} className="flex min-w-0 flex-col rounded-lg border border-line bg-surface-sunken">
                  <header className="sticky top-0 rounded-t-lg border-b border-line bg-surface-sunken/95 px-2.5 py-2 backdrop-blur">
                    <div className="flex items-center gap-1.5">
                      <span aria-hidden className="size-1.5 rounded-full" style={{ background: tone.fg }} />
                      <h2 className="font-ui text-xs font-semibold uppercase tracking-wider" style={{ color: tone.fg }}>
                        {tone.label}
                      </h2>
                      <span className="num ml-auto text-xs text-content-muted">{items.length}</span>
                    </div>
                    <p className="mt-1 num text-xs text-content-faint">
                      {total > 0 ? <Money value={String(total)} compact /> : "\u2014"}
                    </p>
                  </header>
                  <div className="flex-1 space-y-2 p-2">
                    {items.length === 0 ? (
                      <p className="px-1 py-3 text-center text-xs text-content-faint">Empty</p>
                    ) : (
                      items.map((q) => <Card key={q.quote_id} quote={q} />)
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </Async>

      {creating ? <NewQuoteDialog open onOpenChange={setCreating} /> : null}
    </Page>
  );
}
