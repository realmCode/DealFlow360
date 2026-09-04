import { ArrowLeft, Check, CircleAlert, Clock, MessageSquare, Send } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { idempotencyKey } from "@/api/client";
import { dec, formatDate, formatRelative } from "@/api/money";
import { errorHint, errorTitle, isDealFlowError } from "@/api/errors";
import { usePortalMessages, usePortalMutations, usePortalQuote } from "@/api/queries";
import type { CounterOfferLine, NegotiationMessageType } from "@/api/types";
import {
  Button, Dialog, ErrorState, Money, NumericInput, Percent, Qty, Skeleton, Textarea, toast,
} from "@/design-system";
import { cn } from "@/lib/cn";

/**
 * The customer's view of one proposal.
 *
 * Nothing internal appears here — not because it is hidden, but because the
 * `/portal/*` response schemas have no cost, margin or risk field to render.
 */
export function PortalQuotePage() {
  const { quoteId } = useParams<{ quoteId: string }>();
  const quote = usePortalQuote(quoteId);
  const thread = usePortalMessages(quoteId);
  const m = usePortalMutations(quoteId!);

  const [tab, setTab] = React.useState<"terms" | "discuss">("terms");
  const [message, setMessage] = React.useState("");
  const [kind, setKind] = React.useState<NegotiationMessageType>("QUESTION");
  const [counters, setCounters] = React.useState<Record<string, string>>({});
  const [confirming, setConfirming] = React.useState(false);
  const [blocked, setBlocked] = React.useState<unknown>(null);
  const confirmIntent = React.useRef(idempotencyKey("confirm"));

  if (quote.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }
  if (quote.isError) return <ErrorState error={quote.error} onRetry={quote.refetch} />;

  const q = quote.data!;
  const v = q.current_version;
  const lines = v?.lines ?? [];
  const isConfirmed = q.status === "CONFIRMED" || v?.status === "CONFIRMED";
  const counterLines: CounterOfferLine[] = Object.entries(counters)
    .filter(([, val]) => val !== "")
    .map(([quote_line_id, requested_discount_pct]) => ({ quote_line_id, requested_discount_pct }));

  const send = () => {
    const isCounter = counterLines.length > 0;
    m.sendMessage.mutate(
      {
        message_type: isCounter ? "COUNTER_OFFER" : kind,
        body: message.trim() || (isCounter ? "We would like to request the changes shown." : ""),
        ...(isCounter ? { lines: counterLines } : {}),
      },
      {
        onSuccess: (res) => {
          setMessage("");
          setCounters({});
          if (res?.new_version_id) {
            toast.success(
              "Your request was received",
              "A revised version has been prepared and is being reviewed by the team.",
            );
          } else {
            toast.success("Message sent");
          }
          setTab("discuss");
        },
        onError: toast.fromError,
      },
    );
  };

  const confirm = () =>
    m.confirm.mutate(confirmIntent.current, {
      onSuccess: (res) => {
        setConfirming(false);
        toast.success("Order confirmed", res.order?.order_number ? `Reference ${res.order.order_number}.` : undefined);
      },
      onError: (e) => {
        setConfirming(false);
        if (isDealFlowError(e) && e.code === "STALE_APPROVAL") setBlocked(e);
        else toast.fromError(e);
      },
    });

  return (
    <div>
      <Link to="/portal" className="inline-flex items-center gap-1.5 text-sm text-content-muted transition-colors hover:text-ink-900">
        <ArrowLeft className="size-3.5" /> All proposals
      </Link>

      <header className="mt-3 flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="font-ui text-3xl font-semibold tracking-tight text-ink-900">{q.title}</h1>
          <p className="mt-1.5 text-md text-content-secondary">
            <span className="num">{q.quote_number}</span> &middot; version {v?.version_number} &middot; from {q.seller_name}
          </p>
        </div>
        <div className="text-right">
          <div className="micro">Total</div>
          <Money value={v?.total_revenue ?? "0"} currency={v?.currency ?? "USD"} className="font-ui text-4xl font-semibold text-ink-900" />
          {v?.valid_until ? (
            <p className="mt-1 text-sm text-content-muted">Valid until {formatDate(v.valid_until)}</p>
          ) : null}
        </div>
      </header>

      {/* -- blocked / awaiting notice -------------------------------------- */}
      {blocked || (!q.can_confirm && q.blocked_reason) ? (
        <div className="mt-6 flex items-start gap-3 rounded-xl border border-[#e9d8c4] bg-[#fdf8f1] p-5">
          <Clock aria-hidden className="mt-0.5 size-5 shrink-0 text-gov-600" />
          <div>
            <p className="font-ui text-md font-semibold text-ink-900">
              {blocked ? errorTitle(blocked) : "This proposal is not ready to accept yet"}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-content-secondary">
              {blocked
                ? "Your requested changes are being reviewed by our team. We will let you know as soon as the revised terms are ready."
                : q.blocked_reason}
            </p>
          </div>
        </div>
      ) : null}

      {/* -- tabs ------------------------------------------------------------ */}
      <div className="mt-7 flex items-center gap-1 border-b border-[#e8e4dd]">
        {([["terms", "What you are buying"], ["discuss", "Discussion"]] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "relative h-10 cursor-pointer px-3 font-ui text-md font-medium transition-colors",
              "after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:rounded-t-full",
              tab === key ? "text-ink-900 after:bg-accent-600" : "text-content-muted hover:text-ink-900 after:bg-transparent",
            )}
          >
            {label}
            {key === "discuss" && (thread.data?.messages?.length ?? 0) > 0 ? (
              <span className="num ml-1.5 rounded-pill bg-ink-100 px-1.5 text-2xs text-content-muted">
                {thread.data?.messages?.length ?? 0}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {tab === "terms" ? (
        <div className="mt-6 space-y-6">
          <section className="overflow-hidden rounded-xl border border-[#e8e4dd] bg-white">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[#f0ece5] bg-[#fbfaf8]">
                  {["Item", "Quantity", "Unit price", "Amount"].map((h, i) => (
                    <th key={h} className={cn("px-5 py-3 font-ui text-xs font-semibold uppercase tracking-wider text-content-muted", i > 0 && "text-right")}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id} className="border-b border-[#f0ece5] last:border-b-0">
                    <td className="px-5 py-4">
                      <div className="font-ui text-md font-medium text-ink-900">{l.description}</div>
                      {l.billing_type === "RECURRING" ? (
                        <div className="mt-0.5 text-sm text-content-muted">
                          Billed {l.recurring_interval?.toLowerCase()}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-5 py-4 text-right"><Qty value={l.quantity} className="text-md" /></td>
                    <td className="px-5 py-4 text-right">
                      <Money value={l.unit_net_price} currency={v?.currency ?? "USD"} className="text-md" />
                      {dec(l.discount_pct).greaterThan(0) ? (
                        <div className="text-xs text-content-muted">
                          <Percent value={l.discount_pct} dp={1} /> off list
                        </div>
                      ) : null}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <Money value={l.net_amount} currency={v?.currency ?? "USD"} className="text-md font-semibold text-ink-900" />
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-[#fbfaf8]">
                  <td colSpan={3} className="px-5 py-4 text-right font-ui text-md font-semibold text-ink-900">Total</td>
                  <td className="px-5 py-4 text-right">
                    <Money value={v?.total_revenue ?? "0"} currency={v?.currency ?? "USD"} className="font-ui text-xl font-semibold text-ink-900" />
                  </td>
                </tr>
              </tfoot>
            </table>
          </section>

          {/* -- terms ------------------------------------------------------ */}
          <section className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Payment terms", value: v!.payment_terms?.replace(/_/g, " ") ?? "\u2014" },
              { label: "Currency", value: v!.currency },
              { label: "Version", value: `${v?.version_number}` },
            ].map((t) => (
              <div key={t.label} className="rounded-xl border border-[#e8e4dd] bg-white px-5 py-4">
                <div className="micro">{t.label}</div>
                <div className="mt-1 font-ui text-md font-medium text-ink-900">{t.value}</div>
              </div>
            ))}
          </section>

          {/* -- request changes -------------------------------------------- */}
          {q.can_confirm || v?.status === "SENT" || v?.status === "NEGOTIATING" ? (
            <section className="rounded-xl border border-[#e8e4dd] bg-white p-6">
              <h2 className="font-ui text-lg font-semibold text-ink-900">Request a change</h2>
              <p className="mt-1 text-sm leading-relaxed text-content-secondary">
                Ask for a different price on any line. We will prepare a revised version and review it before
                coming back to you.
              </p>
              <ul className="mt-4 space-y-2">
                {lines.map((l) => (
                  <li key={l.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-[#f0ece5] px-4 py-3">
                    <span className="min-w-0 flex-1 truncate font-ui text-md text-ink-900">{l.description}</span>
                    <span className="text-sm text-content-muted">
                      currently <Percent value={l.discount_pct} dp={1} /> off
                    </span>
                    <span className="flex items-center gap-2">
                      <label htmlFor={`counter-${l.id}`} className="text-sm text-content-muted">Request</label>
                      <NumericInput
                        id={`counter-${l.id}`}
                        size="sm"
                        className="w-24"
                        suffix="%"
                        value={counters[l.id] ?? ""}
                        onValueChange={(val) => setCounters((c) => ({ ...c, [l.id]: val }))}
                      />
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-4">
                <Textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Add a note for the team (optional)"
                  aria-label="Message to the seller"
                />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  size="lg"
                  icon={<Send className="size-4" />}
                  loading={m.sendMessage.isPending}
                  disabled={counterLines.length === 0 && !message.trim()}
                  onClick={send}
                >
                  {counterLines.length > 0 ? "Submit request" : "Send message"}
                </Button>
                {counterLines.length === 0 && message.trim() ? (
                  <span className="text-sm text-content-muted">
                    Sent as a{" "}
                    <button
                      type="button"
                      onClick={() => setKind(kind === "QUESTION" ? "COMMENT" : "QUESTION")}
                      className="cursor-pointer underline underline-offset-2"
                    >
                      {kind.toLowerCase()}
                    </button>
                  </span>
                ) : null}
              </div>
            </section>
          ) : null}

          {/* -- confirm ------------------------------------------------------ */}
          <section
            className={cn(
              "flex flex-wrap items-center justify-between gap-4 rounded-xl border p-6",
              q.can_confirm ? "border-[#c9e6d4] bg-[#f4fbf7]" : "border-[#e8e4dd] bg-white",
            )}
          >
            <div className="min-w-0">
              <h2 className="font-ui text-lg font-semibold text-ink-900">
                {isConfirmed ? "This proposal is confirmed" : "Ready to go ahead?"}
              </h2>
              <p className="mt-1 max-w-xl text-sm leading-relaxed text-content-secondary">
                {isConfirmed
                  ? "Thank you. Your order has been created and your account team will be in touch about delivery."
                  : q.can_confirm
                    ? "Accepting creates the order at the terms shown above."
                    : q.blocked_reason ?? "This proposal cannot be accepted in its current state."}
              </p>
            </div>
            {!isConfirmed ? (
              <Button
                variant="approve"
                size="lg"
                icon={<Check className="size-4" />}
                disabled={!q.can_confirm}
                onClick={() => setConfirming(true)}
              >
                Accept proposal
              </Button>
            ) : null}
          </section>
        </div>
      ) : (
        <section className="mt-6 space-y-4">
          {(thread.data?.messages?.length ?? 0) === 0 ? (
            <div className="rounded-xl border border-[#e8e4dd] bg-white p-10 text-center">
              <MessageSquare className="mx-auto size-6 text-content-faint" />
              <p className="mt-3 font-ui text-md font-medium text-ink-900">No messages yet</p>
              <p className="mt-1 text-sm text-content-muted">Anything you send appears here alongside our replies.</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {(thread.data?.messages ?? []).map((msg) => {
                const mine = msg.author_kind === "CUSTOMER";
                return (
                  <li key={msg.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                    <div
                      className={cn(
                        "max-w-[80%] rounded-xl border px-4 py-3",
                        mine ? "border-accent-200 bg-accent-50" : msg.author_kind === "SYSTEM" ? "border-[#e8e4dd] bg-[#fbfaf8]" : "border-[#e8e4dd] bg-white",
                      )}
                    >
                      <div className="flex items-baseline gap-2">
                        <span className="font-ui text-xs font-semibold text-ink-900">
                          {mine ? "You" : msg.author_kind === "SYSTEM" ? "System" : q.seller_name}
                        </span>
                        <span className="text-xs text-content-faint">{formatRelative(msg.created_at)}</span>
                      </div>
                      <p className="mt-1 text-md leading-relaxed text-content">{msg.body}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="rounded-xl border border-[#e8e4dd] bg-white p-5">
            <Textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Write a message…" aria-label="Message" />
            <div className="mt-3 flex justify-end">
              <Button variant="primary" loading={m.sendMessage.isPending} disabled={!message.trim()} onClick={send} icon={<Send className="size-3.5" />}>
                Send
              </Button>
            </div>
          </div>
        </section>
      )}

      <Dialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Accept this proposal"
        description="This creates the order at the terms shown. Your account team will confirm delivery."
        width="sm"
        footer={
          <>
            <Button onClick={() => setConfirming(false)}>Not yet</Button>
            <Button variant="approve" loading={m.confirm.isPending} onClick={confirm}>Accept and create order</Button>
          </>
        }
      >
        <div className="flex items-baseline justify-between border-b border-line pb-3">
          <span className="text-md text-content-secondary">Total</span>
          <Money value={v?.total_revenue ?? "0"} currency={v?.currency ?? "USD"} className="font-ui text-xl font-semibold text-ink-900" />
        </div>
        <p className="mt-3 text-sm leading-relaxed text-content-muted">
          {lines.length} line{lines.length === 1 ? "" : "s"} &middot; payment terms{" "}
          {v?.payment_terms?.replace(/_/g, " ").toLowerCase()}
        </p>
      </Dialog>

      {blocked ? (
        <div className="mt-6 flex items-start gap-3 rounded-xl border border-[#e9d8c4] bg-[#fdf8f1] p-5">
          <CircleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-gov-600" />
          <p className="text-sm leading-relaxed text-content-secondary">{errorHint(blocked)}</p>
        </div>
      ) : null}
    </div>
  );
}
