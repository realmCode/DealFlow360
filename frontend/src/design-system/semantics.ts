/**
 * Backend enum -> visual treatment.
 *
 * Every map here is keyed by a literal the API can return. Adding a value to
 * an enum server-side surfaces as a missing key, not a silently grey badge.
 */
import type {
  ApprovalRequestStatus,
  ApprovalStepStatus,
  AttentionItemType,
  DealStage,
  InvoiceStatus,
  PolicyResultStatus,
  QuoteVersionStatus,
  RiskBand,
  SalesOrderStatus,
  Severity,
} from "@/api/types";

export interface Tone {
  /** Text/rail colour. */
  fg: string;
  /** Tint background. */
  bg: string;
  label: string;
}

const tone = (fg: string, bg: string, label: string): Tone => ({ fg, bg, label });

export const RISK: Record<RiskBand, Tone> = {
  NONE: tone("var(--risk-none)", "var(--risk-none-bg)", "No risk"),
  LOW: tone("var(--risk-low)", "var(--risk-low-bg)", "Low"),
  MEDIUM: tone("var(--risk-medium)", "var(--risk-medium-bg)", "Medium"),
  HIGH: tone("var(--risk-high)", "var(--risk-high-bg)", "High"),
  CRITICAL: tone("var(--risk-critical)", "var(--risk-critical-bg)", "Critical"),
};

export const POLICY: Record<PolicyResultStatus, Tone> = {
  PASSED: tone("var(--policy-passed)", "var(--policy-passed-bg)", "Passed"),
  WARNING: tone("var(--policy-warning)", "var(--policy-warning-bg)", "Warning"),
  VIOLATED: tone("var(--policy-violated)", "var(--policy-violated-bg)", "Violated"),
  NOT_APPLICABLE: tone("var(--policy-na)", "var(--policy-na-bg)", "N/A"),
};

export const SEVERITY: Record<Severity, Tone> = {
  LOW: tone("var(--sev-low)", "var(--sev-low-bg)", "Low"),
  MEDIUM: tone("var(--sev-medium)", "var(--sev-medium-bg)", "Medium"),
  HIGH: tone("var(--sev-high)", "var(--sev-high-bg)", "High"),
  CRITICAL: tone("var(--sev-critical)", "var(--sev-critical-bg)", "Critical"),
};

export const VERSION_STATUS: Record<QuoteVersionStatus, Tone> = {
  DRAFT: tone("var(--state-draft)", "var(--state-draft-bg)", "Draft"),
  PENDING_APPROVAL: tone("var(--state-pending)", "var(--state-pending-bg)", "Pending approval"),
  APPROVED: tone("var(--state-approved)", "var(--state-approved-bg)", "Approved"),
  SENT: tone("var(--state-sent)", "var(--state-sent-bg)", "Sent"),
  NEGOTIATING: tone("var(--state-negotiating)", "var(--state-negotiating-bg)", "Negotiating"),
  CONFIRMED: tone("var(--state-confirmed)", "var(--state-confirmed-bg)", "Confirmed"),
  REJECTED: tone("var(--state-rejected)", "var(--state-rejected-bg)", "Rejected"),
  SUPERSEDED: tone("var(--state-superseded)", "var(--state-superseded-bg)", "Superseded"),
};

export const APPROVAL_STATUS: Record<ApprovalRequestStatus, Tone> = {
  PENDING: tone("var(--state-pending)", "var(--state-pending-bg)", "Pending"),
  APPROVED: tone("var(--state-approved)", "var(--state-approved-bg)", "Approved"),
  REJECTED: tone("var(--state-rejected)", "var(--state-rejected-bg)", "Rejected"),
  REVISION_REQUESTED: tone("var(--state-negotiating)", "var(--state-negotiating-bg)", "Revision requested"),
  STALE: tone("var(--risk-critical)", "var(--risk-critical-bg)", "Stale"),
  CANCELLED: tone("var(--state-superseded)", "var(--state-superseded-bg)", "Cancelled"),
};

export const STEP_STATUS: Record<ApprovalStepStatus, Tone> = {
  PENDING: tone("var(--state-pending)", "var(--state-pending-bg)", "Pending"),
  APPROVED: tone("var(--state-approved)", "var(--state-approved-bg)", "Approved"),
  REJECTED: tone("var(--state-rejected)", "var(--state-rejected-bg)", "Rejected"),
  REVISION_REQUESTED: tone("var(--state-negotiating)", "var(--state-negotiating-bg)", "Revision requested"),
  SKIPPED: tone("var(--state-superseded)", "var(--state-superseded-bg)", "Skipped"),
  STALE: tone("var(--risk-critical)", "var(--risk-critical-bg)", "Invalidated"),
};

export const ORDER_STATUS: Record<SalesOrderStatus, Tone> = {
  CREATED: tone("var(--state-draft)", "var(--state-draft-bg)", "Created"),
  ALLOCATED: tone("var(--state-sent)", "var(--state-sent-bg)", "Allocated"),
  PARTIALLY_ALLOCATED: tone("var(--state-pending)", "var(--state-pending-bg)", "Partly allocated"),
  BACKORDERED: tone("var(--risk-high)", "var(--risk-high-bg)", "Backordered"),
  PARTIALLY_FULFILLED: tone("var(--state-pending)", "var(--state-pending-bg)", "Partly fulfilled"),
  FULFILLED: tone("var(--state-confirmed)", "var(--state-confirmed-bg)", "Fulfilled"),
  CANCELLED: tone("var(--state-superseded)", "var(--state-superseded-bg)", "Cancelled"),
};

export const INVOICE_STATUS: Record<InvoiceStatus, Tone> = {
  DRAFT: tone("var(--state-draft)", "var(--state-draft-bg)", "Draft"),
  ISSUED: tone("var(--state-sent)", "var(--state-sent-bg)", "Issued"),
  PARTIALLY_PAID: tone("var(--state-pending)", "var(--state-pending-bg)", "Part paid"),
  PAID: tone("var(--state-confirmed)", "var(--state-confirmed-bg)", "Paid"),
  OVERDUE: tone("var(--risk-critical)", "var(--risk-critical-bg)", "Overdue"),
  VOID: tone("var(--state-superseded)", "var(--state-superseded-bg)", "Void"),
};

export const DEAL_STAGE: Record<DealStage, Tone> = {
  QUALIFICATION: tone("var(--state-draft)", "var(--state-draft-bg)", "Qualification"),
  PROPOSAL: tone("var(--state-sent)", "var(--state-sent-bg)", "Proposal"),
  NEGOTIATION: tone("var(--state-negotiating)", "var(--state-negotiating-bg)", "Negotiation"),
  CLOSED_WON: tone("var(--state-confirmed)", "var(--state-confirmed-bg)", "Won"),
  CLOSED_LOST: tone("var(--state-rejected)", "var(--state-rejected-bg)", "Lost"),
};

/** Human copy for the 11 attention types. */
export const ATTENTION_LABEL: Record<AttentionItemType, string> = {
  STALE_APPROVAL: "Approval invalidated",
  MARGIN_VIOLATION: "Margin below floor",
  PENDING_APPROVAL: "Awaiting approval",
  INVENTORY_SHORTAGE: "Inventory shortage",
  CUSTOMER_RESPONSE_REQUIRED: "Awaiting customer",
  ORDER_BLOCKED: "Order blocked",
  DISCOUNT_ANOMALY: "Discount anomaly",
  DELIVERY_SLIPPAGE: "Delivery slipping",
  STALLED_DEAL: "Deal stalled",
  APPROVAL_SLA_BREACH: "Approval SLA breached",
  INVENTORY_REORDER_NEEDED: "Reorder needed",
};

/** Turn an enum literal into readable text when no explicit map exists. */
export const humanise = (value?: string | null): string =>
  value
    ? value.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())
    : "\u2014";
