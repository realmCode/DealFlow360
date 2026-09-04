import { ReceiptText } from "lucide-react";
import { formatDate, sortKey } from "@/api/money";
import { useCreditNotes } from "@/api/queries";
import type { CreditNoteRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import { Async, Badge, type Column, DataTable, EmptyState, Money, Panel } from "@/design-system";

const TONE: Record<string, { fg: string; bg: string; label: string }> = {
  DRAFT: { fg: "var(--state-draft)", bg: "var(--state-draft-bg)", label: "Draft" },
  ISSUED: { fg: "var(--state-sent)", bg: "var(--state-sent-bg)", label: "Issued" },
  APPLIED: { fg: "var(--state-confirmed)", bg: "var(--state-confirmed-bg)", label: "Applied" },
  VOID: { fg: "var(--state-superseded)", bg: "var(--state-superseded-bg)", label: "Void" },
};

export function CreditNotesPage() {
  const query = useCreditNotes();

  const columns: Column<CreditNoteRead>[] = [
    {
      id: "number",
      header: "Credit note",
      sortValue: (c) => c.credit_note_number ?? "",
      cell: (c) => <span className="num font-medium text-content">{c.credit_note_number}</span>,
    },
    { id: "reason", header: "Reason", cell: (c) => <span className="capitalize">{c.reason?.replace(/_/g, " ").toLowerCase()}</span> },
    { id: "status", header: "Status", sortValue: (c) => c.status, cell: (c) => <Badge size="sm" tone={TONE[c.status]} /> },
    { id: "issued", header: "Issued", sortValue: (c) => c.issue_date ?? "", cell: (c) => <span className="whitespace-nowrap text-xs">{formatDate(c.issue_date)}</span> },
    { id: "amount", header: "Amount", align: "right", sortValue: (c) => sortKey(c.total_amount), cell: (c) => <Money value={c.total_amount} currency={c.currency} className="font-semibold" /> },
    { id: "refunded", header: "Refunded", align: "right", sortValue: (c) => sortKey(c.amount_refunded ?? 0), cell: (c) => <Money value={c.amount_refunded ?? "0"} currency={c.currency} className="text-content-muted" /> },
  ];

  return (
    <Page title="Credit notes" subtitle="Raised when a subscription is cancelled or downgraded mid-cycle.">
      <Panel>
        <Async
          query={query}
          isEmpty={(d) => d.length === 0}
          empty={
            <EmptyState
              icon={<ReceiptText className="size-5" />}
              title="No credit notes"
              body="A credit note is created automatically when a cancellation leaves an unused portion of a paid period."
            />
          }
        >
          {(rows) => <DataTable rows={rows} columns={columns} caption="Credit notes" getKey={(c) => c.id} rail={(c) => TONE[c.status].fg} />}
        </Async>
      </Panel>
    </Page>
  );
}
