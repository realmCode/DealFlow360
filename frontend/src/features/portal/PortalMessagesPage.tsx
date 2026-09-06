import { MessageSquare } from "lucide-react";
import { Link } from "react-router-dom";
import { usePortalQuotes } from "@/api/queries";
import { Async, EmptyState, Money, Skeleton } from "@/design-system";

/**
 * Messages across every proposal. The backend threads conversation per quote,
 * so this is an index into those threads rather than a separate inbox.
 */
export function PortalMessagesPage() {
  const quotes = usePortalQuotes();

  return (
    <div>
      <header className="mb-7">
        <h1 className="font-ui text-3xl font-semibold tracking-tight text-ink-900">Messages</h1>
        <p className="mt-2 max-w-2xl text-lg leading-relaxed text-content-secondary">
          Each proposal has its own conversation with your account team. Open one to read the thread or reply.
        </p>
      </header>

      <Async
        query={quotes}
        skeleton={<div className="space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}</div>}
        isEmpty={(d) => d.length === 0}
        empty={
          <div className="rounded-xl border border-[#e8e4dd] bg-white p-12">
            <EmptyState icon={<MessageSquare className="size-5" />} title="No conversations yet" body="Threads open once a proposal is issued to you." />
          </div>
        }
      >
        {(list) => (
          <ul className="space-y-3">
            {list.map((q) => (
              <li key={q.quote_id}>
                <Link
                  to={`/portal/quotes/${q.quote_id}`}
                  className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[#e8e4dd] bg-white p-5 transition-all duration-base hover:border-accent-400 hover:shadow-pop"
                >
                  <div className="min-w-0">
                    <p className="font-ui text-md font-semibold text-ink-900">{q.title}</p>
                    <p className="mt-0.5 text-sm text-content-muted">
                      <span className="num">{q.quote_number}</span> &middot; version {q.version_number}
                      {q.awaiting_customer ? " \u00b7 awaiting your response" : ""}
                    </p>
                  </div>
                  <div className="text-right">
                    <Money value={q.total_revenue} currency={q.currency} className="font-ui text-lg font-semibold text-ink-900" />
                    <p className="text-xs text-content-faint">version {q.version_number}</p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Async>
    </div>
  );
}
