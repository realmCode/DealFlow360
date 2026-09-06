import { ArrowRight, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { formatDate } from "@/api/money";
import { usePortalQuotes } from "@/api/queries";
import { Async, EmptyState, Money, Skeleton } from "@/design-system";

/**
 * The customer's list of proposals.
 *
 * Deliberately low density: generous spacing, larger type, no table. This is
 * something you read, not something you operate.
 */
const STATE_COPY: Record<string, { label: string; tone: string }> = {
  SENT: { label: "Awaiting your review", tone: "var(--accent-600)" },
  NEGOTIATING: { label: "In discussion", tone: "#7c3aed" },
  APPROVED: { label: "Ready for you", tone: "var(--accent-600)" },
  CONFIRMED: { label: "Confirmed", tone: "var(--policy-passed)" },
  SUPERSEDED: { label: "Replaced by a newer version", tone: "var(--ink-400)" },
  REJECTED: { label: "Withdrawn", tone: "var(--ink-400)" },
};

export function PortalQuotesPage() {
  const query = usePortalQuotes();

  return (
    <div>
      <header className="mb-7">
        <h1 className="font-ui text-3xl font-semibold tracking-tight text-ink-900">Your proposals</h1>
        <p className="mt-2 max-w-2xl text-lg leading-relaxed text-content-secondary">
          Everything your account team has issued to you. Open one to review the terms, ask a question, or
          request a change.
        </p>
      </header>

      <Async
        query={query}
        skeleton={<div className="space-y-4">{[0, 1].map((i) => <Skeleton key={i} className="h-32 w-full rounded-xl" />)}</div>}
        isEmpty={(d) => d.length === 0}
        empty={
          <div className="rounded-xl border border-[#e8e4dd] bg-white p-12">
            <EmptyState
              icon={<FileText className="size-5" />}
              title="No proposals yet"
              body="When your account team issues a quotation it will appear here."
            />
          </div>
        }
      >
        {(quotes) => (
          <ul className="space-y-4">
            {quotes.map((q) => {
              const state = STATE_COPY[q.status] ?? { label: q.status, tone: "var(--ink-400)" };
              return (
                <li key={q.quote_id}>
                  <Link
                    to={`/portal/quotes/${q.quote_id}`}
                    className="group block rounded-xl border border-[#e8e4dd] bg-white p-6 transition-all duration-base hover:border-accent-400 hover:shadow-pop"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2.5">
                          <span
                            className="inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-ui text-xs font-semibold"
                            style={{ color: state.tone, background: `${state.tone}14` }}
                          >
                            <span aria-hidden className="size-1.5 rounded-full" style={{ background: state.tone }} />
                            {state.label}
                          </span>
                          <span className="num text-sm text-content-muted">{q.quote_number}</span>
                        </div>
                        <h2 className="mt-2.5 font-ui text-xl font-semibold tracking-tight text-ink-900">
                          {q.title}
                        </h2>
                        {q.valid_until ? (
                          <p className="mt-1 text-sm text-content-muted">Valid until {formatDate(q.valid_until)}</p>
                        ) : null}
                      </div>

                      <div className="text-right">
                        <div className="micro">Total</div>
                        <Money
                          value={q.total_revenue}
                          currency={q.currency}
                          className="font-ui text-2xl font-semibold text-ink-900"
                        />
                        <div className="mt-0.5 text-xs text-content-muted">Version {q.version_number}</div>
                      </div>
                    </div>

                    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#f0ece5] pt-4">
                      <p className="text-sm text-content-secondary">
                        {q.can_confirm
                          ? "Ready for you to accept."
                          : q.blocked_reason ?? "No action needed from you right now."}
                      </p>
                      <span className="inline-flex items-center gap-1.5 font-ui text-sm font-medium text-accent-700 transition-transform duration-fast group-hover:translate-x-0.5">
                        {q.awaiting_customer ? "Review and respond" : "View proposal"}
                        <ArrowRight className="size-3.5" />
                      </span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Async>
    </div>
  );
}
