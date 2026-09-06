import { BellRing, CheckCircle2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { formatRelative } from "@/api/money";
import { useAttentionAction, useAttentionItems } from "@/api/queries";
import type { AttentionItemRead, Severity } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  ATTENTION_LABEL, Async, Button, EmptyState, Panel, SEVERITY, Segmented, SeverityBadge,
  Select, toast,
} from "@/design-system";

const targetFor = (i: AttentionItemRead) =>
  i.source_type === "approval_request" ? `/approvals/${i.source_id}`
  : i.quote_id ? `/quotes/${i.quote_id}`
  : i.source_type === "sales_order" ? `/orders/${i.source_id}`
  : null;

export function AttentionPage() {
  const [status, setStatus] = React.useState<"OPEN" | "ACKNOWLEDGED" | "RESOLVED">("OPEN");
  const [severity, setSeverity] = React.useState("");
  const query = useAttentionItems({ status, ...(severity ? { severity } : {}) });
  const act = useAttentionAction();

  const run = (id: string, action: "acknowledge" | "resolve" | "nudge" | "escalate", label: string) =>
    act.mutate({ id, action }, { onSuccess: () => toast.success(label), onError: toast.fromError });

  return (
    <Page
      title="Attention items"
      subtitle="Every signal the engine raised, with the reason, the impact and the owner it belongs to."
    >
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <Segmented
            ariaLabel="Item status"
            value={status}
            onValueChange={setStatus}
            options={[
              { value: "OPEN", label: "Open" },
              { value: "ACKNOWLEDGED", label: "Acknowledged" },
              { value: "RESOLVED", label: "Resolved" },
            ]}
          />
          <Select
            size="sm"
            className="w-40"
            value={severity}
            onValueChange={setSeverity}
            ariaLabel="Filter by severity"
            placeholder="Any severity"
            options={[
              { value: "", label: "Any severity" },
              ...(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as Severity[]).map((s) => ({ value: s, label: SEVERITY[s].label })),
            ]}
          />
          <span className="ml-auto text-xs text-content-muted">{query.data?.length ?? 0} items</span>
        </div>

        <Async
          query={query}
          isEmpty={(d) => d.length === 0}
          empty={
            <EmptyState
              icon={<CheckCircle2 className="size-5" />}
              title={status === "OPEN" ? "Nothing open" : `No ${status.toLowerCase()} items`}
              body={status === "OPEN" ? "Every deal is inside policy." : undefined}
            />
          }
        >
          {(items) => (
            <ul>
              {items.map((i) => {
                const tone = SEVERITY[i.severity];
                const to = targetFor(i);
                return (
                  <li key={i.id} className="relative border-b border-line/70 py-3 pl-4 pr-3 last:border-b-0">
                    <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: tone.fg }} />

                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge value={i.severity} size="sm" />
                      <span className="font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint">
                        {ATTENTION_LABEL[i.type]}
                      </span>
                      {i.owner_role ? (
                        <span className="rounded-sm border border-line px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wider text-content-muted">
                          {i.owner_role}
                        </span>
                      ) : null}
                      <span className="ml-auto text-xs text-content-faint">{formatRelative(i.created_at)}</span>
                    </div>

                    <h3 className="mt-1 font-ui text-md font-semibold text-content">{i.title}</h3>

                    <dl className="mt-1.5 grid gap-1 sm:grid-cols-[auto_minmax(0,1fr)]">
                      {[["Why", i.reason], ["Impact", i.impact], ["Do", i.recommended_action]].map(([k, val]) => (
                        <React.Fragment key={k}>
                          <dt className="text-sm text-content-faint sm:w-14">{k}</dt>
                          <dd className={`text-sm leading-[18px] ${k === "Do" ? "font-medium text-content" : "text-content-secondary"}`}>
                            {val}
                          </dd>
                        </React.Fragment>
                      ))}
                    </dl>

                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {to ? (
                        <Button size="xs" variant="secondary" asChild>
                          <Link to={to}>Open</Link>
                        </Button>
                      ) : null}
                      {i.status === "OPEN" ? (
                        <Button size="xs" variant="ghost" onClick={() => run(i.id, "acknowledge", "Acknowledged")}>
                          Acknowledge
                        </Button>
                      ) : null}
                      {i.status !== "RESOLVED" ? (
                        <>
                          <Button size="xs" variant="ghost" onClick={() => run(i.id, "nudge", "Owner nudged")}>
                            Nudge owner
                          </Button>
                          <Button size="xs" variant="ghost" onClick={() => run(i.id, "escalate", "Escalated")}>
                            Escalate
                          </Button>
                          <Button size="xs" variant="ghost" onClick={() => run(i.id, "resolve", "Resolved")}>
                            Resolve
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Async>
      </Panel>

      <p className="mt-2 flex items-center gap-1.5 px-1 text-xs text-content-faint">
        <BellRing className="size-3.5" />
        Items resolve themselves when the underlying condition clears — resolving here is for the ones that need a human call.
      </p>
    </Page>
  );
}
