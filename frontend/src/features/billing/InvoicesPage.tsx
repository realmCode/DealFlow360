import { FileText, Plus } from "lucide-react";
import * as React from "react";
import { dec, formatDate, sortKey } from "@/api/money";
import { useBillingMutations, useInvoices, useSchedules } from "@/api/queries";
import type { InvoiceRead, PaymentMethod } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, Button, type Column, DataTable, Dialog, EmptyState, FormField, INVOICE_STATUS,
  InvoiceStatusBadge, Metric, Money, NumericInput, Panel, Select, toast,
} from "@/design-system";

const METHODS: PaymentMethod[] = ["BANK_TRANSFER", "CARD", "CHECK", "ACH", "OTHER"];

export function InvoicesPage() {
  const can = useCan();
  const invoices = useInvoices();
  const schedules = useSchedules();
  const { issueInvoice, recordPayment, voidInvoice } = useBillingMutations();

  const [issuing, setIssuing] = React.useState(false);
  const [scheduleId, setScheduleId] = React.useState("");
  const [paying, setPaying] = React.useState<InvoiceRead | null>(null);
  const [amount, setAmount] = React.useState("");
  const [method, setMethod] = React.useState<PaymentMethod>("BANK_TRANSFER");

  const rows = invoices.data ?? [];
  const total = rows.reduce((t, i) => t.plus(dec(i.total_amount)), dec(0)).toString();
  const outstanding = rows
    .filter((i) => i.status !== "PAID" && i.status !== "VOID")
    .reduce((t, i) => t.plus(dec(i.amount_due ?? i.total_amount)), dec(0))
    .toString();
  const overdue = rows.filter((i) => i.is_overdue).length;

  const billable = (schedules.data ?? []).filter((s) => s.status === "SCHEDULED" || s.status === "ACTIVE");

  const columns: Column<InvoiceRead>[] = [
    {
      id: "number",
      header: "Invoice",
      sortValue: (i) => i.invoice_number,
      cell: (i) => (
        <div>
          <div className="num font-medium text-content">{i.invoice_number}</div>
          <div className="num text-2xs text-content-faint">{i.sales_order_id ? "order-linked" : ""}</div>
        </div>
      ),
    },
    {
      id: "status",
      header: "Status",
      sortValue: (i) => i.status,
      cell: (i) => (
        <span className="flex items-center gap-1.5">
          <InvoiceStatusBadge value={i.status} size="sm" />
          {i.is_overdue ? (
            <Badge size="sm" tone={{ fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: `${i.days_overdue}d overdue` }} />
          ) : null}
        </span>
      ),
    },
    { id: "issued", header: "Issued", sortValue: (i) => i.issue_date ?? "", cell: (i) => <span className="whitespace-nowrap text-xs">{formatDate(i.issue_date)}</span>, hideBelow: "md" },
    { id: "due", header: "Due", sortValue: (i) => i.due_date ?? "", cell: (i) => <span className="whitespace-nowrap text-xs">{formatDate(i.due_date)}</span> },
    { id: "amount", header: "Amount", align: "right", sortValue: (i) => sortKey(i.total_amount), cell: (i) => <Money value={i.total_amount} currency={i.currency} className="font-semibold" /> },
    { id: "paid", header: "Paid", align: "right", sortValue: (i) => sortKey(i.amount_paid ?? 0), cell: (i) => <Money value={i.amount_paid ?? "0"} currency={i.currency} className="text-content-muted" />, hideBelow: "sm" },
    { id: "due_amt", header: "Outstanding", align: "right", sortValue: (i) => sortKey(i.amount_due ?? 0), cell: (i) => <Money value={i.amount_due ?? "0"} currency={i.currency} /> },
    ...(can.billing
      ? [{
          id: "act",
          header: "",
          align: "right" as const,
          cell: (i: InvoiceRead) =>
            i.status !== "PAID" && i.status !== "VOID" ? (
              <span className="flex justify-end gap-1">
                <Button size="xs" variant="ghost" onClick={() => { setPaying(i); setAmount(dec(i.amount_due ?? i.total_amount).toString()); }}>
                  Record payment
                </Button>
                <Button
                  size="xs" variant="ghost"
                  onClick={() =>
                    voidInvoice.mutate({ invoiceId: i.id, reason: "Issued in error" }, {
                      onSuccess: () => toast.success("Invoice voided"),
                      onError: toast.fromError,
                    })
                  }
                >
                  Void
                </Button>
              </span>
            ) : null,
        }]
      : []),
  ];

  return (
    <Page
      title="Invoices"
      subtitle="Issued from billing schedules. Overdue is computed from the due date, not stored as a status."
      actions={
        can.billing ? (
          <Button variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setIssuing(true)}>
            Issue invoice
          </Button>
        ) : null
      }
    >
      <div className="mb-3 grid gap-2 sm:grid-cols-3">
        <Panel className="px-3.5 py-2.5"><Metric label="Invoiced" size="lg"><Money value={total} /></Metric></Panel>
        <Panel rail={dec(outstanding).greaterThan(0) ? "var(--gov-500)" : undefined} className="px-3.5 py-2.5">
          <Metric label="Outstanding" size="lg"><Money value={outstanding} /></Metric>
        </Panel>
        <Panel rail={overdue ? "var(--risk-critical)" : undefined} className="px-3.5 py-2.5">
          <Metric label="Overdue" size="lg" tone={overdue ? "var(--risk-critical)" : undefined}>{overdue}</Metric>
        </Panel>
      </div>

      <Panel>
        <Async
          query={invoices}
          isEmpty={(d) => d.length === 0}
          empty={<EmptyState icon={<FileText className="size-5" />} title="No invoices yet" body="Issue one from a billing schedule to start the receivable." />}
        >
          {() => (
            <DataTable
              rows={rows}
              columns={columns}
              caption="Invoices"
              getKey={(i) => i.id}
              rail={(i) => (i.is_overdue ? "var(--risk-critical)" : INVOICE_STATUS[i.status].fg)}
            />
          )}
        </Async>
      </Panel>

      <Dialog
        open={issuing}
        onOpenChange={setIssuing}
        title="Issue an invoice"
        description="Pick the billing schedule to invoice. One invoice per schedule period."
        footer={
          <>
            <Button onClick={() => setIssuing(false)}>Cancel</Button>
            <Button
              variant="primary" loading={issueInvoice.isPending} disabled={!scheduleId}
              onClick={() =>
                issueInvoice.mutate({ billing_schedule_id: scheduleId }, {
                  onSuccess: (inv) => { setIssuing(false); setScheduleId(""); toast.success(`Invoice ${inv.invoice_number} issued`); },
                  onError: toast.fromError,
                })
              }
            >
              Issue
            </Button>
          </>
        }
      >
        <FormField label="Billing schedule" required>
          {(p) => (
            <Select
              id={p.id}
              value={scheduleId}
              onValueChange={setScheduleId}
              placeholder={billable.length ? "Choose a schedule" : "No uninvoiced schedules"}
              options={billable.map((s) => ({
                value: s.id,
                label: `${s.schedule_number} \u2014 ${s.description ?? ""}`,
                hint: dec(s.total_amount).toFixed(2),
              }))}
            />
          )}
        </FormField>
      </Dialog>

      <Dialog
        open={paying !== null}
        onOpenChange={(v) => !v && setPaying(null)}
        title="Record a payment"
        description="This records cash received. DealFlow360 does not process payments."
        width="sm"
        footer={
          <>
            <Button onClick={() => setPaying(null)}>Cancel</Button>
            <Button
              variant="primary" loading={recordPayment.isPending} disabled={!amount}
              onClick={() =>
                paying &&
                recordPayment.mutate(
                  { invoiceId: paying.id, body: { amount, method } },
                  {
                    onSuccess: () => { setPaying(null); toast.success("Payment recorded"); },
                    onError: toast.fromError,
                  },
                )
              }
            >
              Record payment
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <FormField label="Amount" required hint={paying ? `Outstanding ${dec(paying.amount_due ?? paying.total_amount).toFixed(2)}` : undefined}>
            {(p) => <NumericInput id={p.id} value={amount} onValueChange={setAmount} />}
          </FormField>
          <FormField label="Method">
            {(p) => (
              <Select
                id={p.id}
                value={method}
                onValueChange={(v) => setMethod(v as PaymentMethod)}
                options={METHODS.map((v) => ({ value: v, label: v.replace(/_/g, " ").toLowerCase() }))}
              />
            )}
          </FormField>
        </div>
      </Dialog>
    </Page>
  );
}
