import { CheckCircle2, Inbox } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { formatRelative, sortKey } from "@/api/money";
import { useApprovalInbox } from "@/api/queries";
import type { ApprovalInboxItem } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, CellStack, type Column, DataTable, EmptyState, Money, Panel, PermissionState,
  Percent, RiskBadge, Score,
} from "@/design-system";

const bandFor = (score: string) => {
  const s = Number(score);
  return s >= 75 ? "CRITICAL" : s >= 50 ? "HIGH" : s >= 25 ? "MEDIUM" : s > 0 ? "LOW" : "NONE";
};

export function ApprovalsPage() {
  const nav = useNavigate();
  const can = useCan();
  const query = useApprovalInbox(can.approve);

  if (!can.approve) return <PermissionState need="Manager, Finance or Admin" />;

  const columns: Column<ApprovalInboxItem>[] = [
    {
      id: "quote",
      header: "Quotation",
      sortValue: (a) => a.quote_number,
      cell: (a) => (
        <div className="flex items-center gap-2">
          <CellStack top={<span className="num">{a.quote_number} <span className="text-xs font-normal text-content-faint">v{a.version_number}</span></span>} bottom={a.title} />
          {a.is_reapproval ? (
            <Badge
              size="sm"
              tone={{ fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: "Re-approval" }}
            />
          ) : null}
        </div>
      ),
    },
    {
      id: "customer",
      header: "Customer",
      sortValue: (a) => a.customer_name ?? "",
      cell: (a) => <span className="truncate">{a.customer_name}</span>,
      hideBelow: "md",
    },
    {
      id: "level",
      header: "Your step",
      sortValue: (a) => a.sequence,
      cell: (a) => (
        <span className="inline-flex items-center gap-1.5">
          <span className="num text-xs text-content-faint">{a.sequence}</span>
          <span className="font-medium">{a.level.replace(/_/g, " ")}</span>
        </span>
      ),
    },
    {
      id: "value",
      header: "Value",
      align: "right",
      sortValue: (a) => sortKey(a.total_revenue),
      cell: (a) => <Money value={a.total_revenue} className="font-semibold" />,
    },
    {
      id: "margin",
      header: "Margin",
      align: "right",
      sortValue: (a) => sortKey(a.margin_pct),
      cell: (a) => <Percent value={a.margin_pct} dp={1} />,
      hideBelow: "sm",
    },
    {
      id: "risk",
      header: "Risk",
      align: "right",
      sortValue: (a) => sortKey(a.blended_risk_score),
      cell: (a) => (
        <span className="inline-flex items-center gap-1.5">
          <Score value={a.blended_risk_score} dp={1} className="text-xs text-content-muted" />
          <RiskBadge value={bandFor(a.blended_risk_score)} size="sm" dot={false} />
        </span>
      ),
    },
    {
      id: "why",
      header: "Why it needs you",
      cell: (a) => <span className="line-clamp-2 max-w-[420px] text-xs text-content-secondary">{a.reason}</span>,
      hideBelow: "xl",
    },
    {
      id: "waiting",
      header: "Waiting",
      align: "right",
      sortValue: (a) => a.waiting_since ?? "",
      cell: (a) => <span className="whitespace-nowrap text-xs text-content-muted">{formatRelative(a.waiting_since)}</span>,
    },
  ];

  return (
    <Page
      title="Approval inbox"
      subtitle="Quotations waiting on your decision, and the reason each one was routed to you."
    >
      <Panel>
        <Async
          query={query}
          isEmpty={(d) => d.length === 0}
          empty={
            <EmptyState
              icon={<CheckCircle2 className="size-5" />}
              title="Your inbox is clear"
              body="Nothing is waiting on your decision. Items appear here the moment the policy engine routes one to your level."
            />
          }
        >
          {(items) => (
            <DataTable
              rows={items}
              columns={columns}
              caption="Approvals awaiting your decision"
              getKey={(a) => a.approval_step_id}
              onRowClick={(a) => nav(`/approvals/${a.approval_request_id}`)}
              rail={(a) => (a.is_reapproval ? "var(--risk-critical)" : "var(--state-pending)")}
            />
          )}
        </Async>
      </Panel>

      <p className="mt-2 flex items-center gap-1.5 px-1 text-xs text-content-faint">
        <Inbox className="size-3.5" />
        You cannot approve a quotation you authored — the backend enforces separation of duties.
      </p>
    </Page>
  );
}
