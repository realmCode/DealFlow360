import { History } from "lucide-react";
import * as React from "react";
import { formatDateTime, formatRelative } from "@/api/money";
import { useAuditEvents } from "@/api/queries";
import { Page } from "@/app/shells/InternalShell";
import { Async, Button, EmptyState, Panel, SearchInput, Segmented, Skeleton } from "@/design-system";
import { EVENT_TONE } from "./eventTone";

const PAGE = 50;

export function ActivityPage() {
  const [offset, setOffset] = React.useState(0);
  const [search, setSearch] = React.useState("");
  // An activity feed reads newest-first; the API exposes the ordering directly.
  const [order, setOrder] = React.useState<"newest" | "oldest">("newest");
  const query = useAuditEvents({ limit: PAGE, offset, newest_first: order === "newest" });
  const deferred = React.useDeferredValue(search);

  const rows = React.useMemo(() => {
    const items = query.data?.items ?? [];
    const term = deferred.trim().toLowerCase();
    if (!term) return items;
    return items.filter(
      (e) =>
        e.event_type.toLowerCase().includes(term) ||
        (e.actor_email ?? "").toLowerCase().includes(term) ||
        (e.entity_type ?? "").toLowerCase().includes(term),
    );
  }, [query.data, deferred]);

  const total = query.data?.total ?? 0;

  return (
    <Page
      title="Activity"
      subtitle="The append-only audit trail. Every business event carries its actor, role and timestamp."
    >
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <SearchInput value={search} onValueChange={setSearch} placeholder="Filter by event, actor or entity" className="w-full max-w-xs" />
          <Segmented
            ariaLabel="Ordering"
            value={order}
            onValueChange={(v) => { setOrder(v); setOffset(0); }}
            options={[{ value: "newest", label: "Newest first" }, { value: "oldest", label: "Oldest first" }]}
          />
          <span className="ml-auto num text-xs text-content-muted">
            {offset + 1}&ndash;{Math.min(offset + PAGE, total)} of {total}
          </span>
          <div className="flex gap-1">
            <Button size="sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>Previous</Button>
            <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset((o) => o + PAGE)}>Next</Button>
          </div>
        </div>

        <Async
          query={query}
          skeleton={<div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>}
          isEmpty={() => rows.length === 0}
          empty={<EmptyState icon={<History className="size-5" />} title="No events" body="Activity appears here as soon as anything happens in the workspace." />}
        >
          {() => (
            <ul className="divide-y divide-line/60">
              {rows.map((e) => (
                <li key={e.id} className="flex items-center gap-3 px-4 py-2">
                  <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: EVENT_TONE(e.event_type) }} />
                  <span className="num w-12 shrink-0 text-2xs text-content-faint">#{e.sequence}</span>
                  <span className="min-w-0 flex-1 truncate font-ui text-sm font-medium text-content">
                    {e.event_type.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())}
                  </span>
                  <span className="hidden w-32 shrink-0 truncate text-xs text-content-muted sm:block">{e.entity_type}</span>
                  <span className="hidden w-52 shrink-0 truncate text-xs text-content-secondary md:block">{e.actor_email ?? "system"}</span>
                  <span className="hidden w-20 shrink-0 text-2xs uppercase tracking-wide text-content-faint lg:block">{e.actor_role}</span>
                  <span className="shrink-0 whitespace-nowrap text-xs text-content-faint" title={formatDateTime(e.occurred_at)}>
                    {formatRelative(e.occurred_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Async>
      </Panel>
    </Page>
  );
}
