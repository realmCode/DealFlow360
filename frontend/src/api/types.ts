/**
 * Friendly aliases over the generated OpenAPI schema.
 *
 * Nothing here is hand-written: every alias points at a schema the backend
 * actually publishes, so a contract change surfaces as a type error.
 */
import type { components } from "./generated/schema";

type S = components["schemas"];

/* -- identity ------------------------------------------------------------- */
export type LoginRequest = S["LoginRequest"];
export type LoginResponse = S["LoginResponse"];
export type SignupRequest = S["SignupRequest"];
export type TokenPair = S["TokenPair"];
export type AuthenticatedUser = S["AuthenticatedUser"];
export type UserRead = S["UserRead"];
export type UserCreate = S["UserCreate"];
export type RoleCode = S["RoleCode"];

/* -- commercial ----------------------------------------------------------- */
export type CustomerProfileRead = S["CustomerProfileRead"];
export type CustomerProfileCreate = S["CustomerProfileCreate"];
export type CustomerProfileUpdate = S["CustomerProfileUpdate"];
export type ContactRead = S["ContactRead"];
export type ProductRead = S["ProductRead"];
export type ProductCategory = S["ProductCategory"];
export type ProductCreate = S["ProductCreate"];
export type ProductUpdate = S["ProductUpdate"];
export type ProductVariantRead = S["ProductVariantRead"];
export type PriceListRead = S["PriceListRead"];
export type DealRead = S["DealRead"];
export type DealCreate = S["DealCreate"];
export type DealUpdate = S["DealUpdate"];
export type DealStage = S["DealStage"];

/* -- quotes --------------------------------------------------------------- */
export type QuoteRead = S["QuoteRead"];
export type QuoteCreate = S["QuoteCreate"];
export type QuoteListItem = S["QuoteListItem"];
export type QuoteVersionRead = S["QuoteVersionRead"];
export type QuoteVersionSummary = S["QuoteVersionSummary"];
export type QuoteVersionStatus = S["QuoteVersionStatus"];
export type QuoteVersionSource = S["QuoteVersionSource"];
export type QuoteStatus = S["QuoteStatus"];
export type QuoteLineRead = S["QuoteLineRead"];
export type QuoteLineCreate = S["QuoteLineCreate"];
export type QuoteLineUpdate = S["QuoteLineUpdate"];
export type OrderDiscountUpdate = S["OrderDiscountUpdate"];

/* -- policy / risk / decision fabric -------------------------------------- */
export type PolicyRead = S["PolicyRead"];
export type PolicyCreate = S["PolicyCreate"];
export type PolicyUpdate = S["PolicyUpdate"];
export type PolicyType = S["PolicyType"];
export type PolicyResultRead = S["PolicyResultRead"];
export type PolicyEvaluationRead = S["PolicyEvaluationRead"];
export type PolicyResultStatus = S["PolicyResultStatus"];
export type RiskBand = S["RiskBand"];
export type BlendedRiskRead = S["BlendedRiskRead"];
export type RiskComponentRead = S["RiskComponent"];
export type RequiredApproval = S["RequiredApproval"];
export type ImpactRead = S["DecisionFabricResult"];
export type ChangeRead = S["FieldChange"];
export type MaterialChangeRead = S["MaterialChange"];
export type StaleDecisionRead = S["StaleDecision"];
export type SimulationRequest = S["SimulationRequest"];
export type SimulationResult = S["SimulationResult"];
/* `GET /quotes/{id}/recommendations` and `GET /quote-versions/{id}/approval`
   are declared as bare objects in the OpenAPI document. Their real shapes were
   captured from the live API during the Phase 0 audit and are declared here. */
export interface RecommendationRead {
  kind: string;
  product_id: string;
  product_name: string;
  suggested_quantity: string;
  estimated_revenue: string;
  estimated_margin: string;
  estimated_margin_pct: string;
  reason: string;
  impact: string;
  confidence: string;
  is_promoted: boolean;
  detail?: Record<string, unknown>;
}
export interface RecommendationsRead {
  quote_id: string;
  quote_version_id: string;
  recommendations: RecommendationRead[];
}

/* -- approvals ------------------------------------------------------------ */
export type ApprovalRequestRead = S["ApprovalRequestRead"];
export type ApprovalStepRead = S["ApprovalStepRead"];
export type ApprovalDecisionRead = S["ApprovalDecisionRead"];
export type ApprovalInboxItem = S["ApprovalInboxItem"];
export type ApprovalActionRequest = S["ApprovalActionRequest"];
export type ApprovalActionResponse = S["ApprovalActionResponse"];
export type ApprovalRequestStatus = S["ApprovalRequestStatus"];
export type ApprovalStepStatus = S["ApprovalStepStatus"];
export type ApprovalLevel = S["ApprovalLevel"];
/* `/quote-versions/{id}/approval` returns a TRIMMED view, not a full
   ApprovalRequestRead: its steps carry no id, and the request omits the
   decisions, financials and timestamps. Verified against the live API. */
export interface QuoteVersionApprovalStep {
  sequence: number;
  level: ApprovalLevel;
  required_role: RoleCode;
  status: ApprovalStepStatus;
}
export interface QuoteVersionApprovalRequest {
  id: string;
  status: ApprovalRequestStatus;
  reason: string;
  current_step_sequence: number;
  stale_reason?: string | null;
  steps: QuoteVersionApprovalStep[];
}
export interface QuoteVersionApproval {
  quote_version_id: string;
  requires_approval: boolean;
  approval_request: QuoteVersionApprovalRequest | null;
}

/* -- negotiation / portal ------------------------------------------------- */
export type PortalQuoteListItem = S["QuotePublicSummary"];
export type PortalQuoteRead = S["QuotePublicRead"];
export type PortalMessageCreate = S["PortalMessageCreate"];
export type CounterOfferLine = S["CounterOfferLine"];
export type CounterOfferOutcome = S["CounterOfferOutcome"];
export type NegotiationThreadRead = S["NegotiationThreadRead"];
export type NegotiationMessageRead = S["NegotiationMessageRead"];
export type NegotiationMessageType = S["NegotiationMessageType"];
export type ConfirmationResult = S["ConfirmResponse"];

/* -- orders / inventory --------------------------------------------------- */
export type SalesOrderRead = S["SalesOrderRead"];
export type SalesOrderSummary = S["SalesOrderSummary"];
export type SalesOrderLineRead = S["SalesOrderLineRead"];
export type SalesOrderStatus = S["SalesOrderStatus"];
export type AllocationRequest = S["AllocateRequest"];
export type AllocationResult = S["AllocationResult"];
export type AllocationLineResult = S["AllocationPlanLine"];
export type AllocationRead = S["AllocationRead"];
export type AllocationSplit = NonNullable<AllocationLineResult["splits"]>[number];
export type InventoryRead = S["InventoryRead"];
export type WarehouseRead = S["WarehouseRead"];
export type WarehouseCreate = S["WarehouseCreate"];
export type WarehouseUpdate = S["WarehouseUpdate"];
export type FulfillmentRead = S["FulfillmentRead"];

/* -- billing -------------------------------------------------------------- */
export type BillingScheduleRead = S["BillingScheduleRead"];
export type BillingSummaryRead = S["BillingSummary"];
export type BillingType = S["BillingType"];
export type RecurringInterval = S["RecurringInterval"];
export type InvoiceRead = S["InvoiceRead"];
export type InvoiceCreate = S["InvoiceCreate"];
export type InvoiceStatus = S["InvoiceStatus"];
export type PaymentRead = S["PaymentRead"];
export type PaymentCreate = S["PaymentCreate"];
export type PaymentMethod = S["PaymentMethod"];
export type CreditNoteRead = S["CreditNoteRead"];
export type SubscriptionChangeResult = S["SubscriptionChangeResponse"];

/* -- intelligence --------------------------------------------------------- */
export type ControlTowerRead = S["ControlTowerRead"];
export type AttentionItemRead = S["AttentionItemRead"];
export type AttentionItemType = S["AttentionItemType"];
export type Severity = S["Severity"];
export type DealHealthRead = S["DealHealthRead"];
export type DealHealthListRead = S["DealHealthList"];
export type HealthSignalRead = S["DealHealthSignal"];
export type AuditEventRead = S["AuditEventRead"];
export type OrganizationSettingsRead = S["OrganizationSettingsRead"];
export type OrganizationSettingsUpdate = S["OrganizationSettingsUpdate"];
export type SalesTeamRead = S["SalesTeamRead"];

/* -- reporting ------------------------------------------------------------ */
export type PipelineReport = S["PipelineReport"];
export type SalesPerformanceReport = S["SalesPerformanceReport"];
export type DiscountReport = S["DiscountReport"];
export type ApprovalStatusReport = S["ApprovalStatusReport"];
export type ReportRowRead = S["ReportRowRead"];
export type ProductReportEntry = S["ProductReportEntry"];
export type DiscountByRep = S["DiscountByRep"];
export type SalesTeamMemberRead = S["SalesTeamMemberRead"];
export type ProductReport = S["ProductReport"];
export type DiscountAnomalyReport = S["DiscountAnomalyList"];
export type DiscountAnomalyRead = S["DiscountAnomalyRead"];

/* -- envelopes ------------------------------------------------------------ */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** An API money/percentage/quantity value. Always a string — never a number. */
export type Numeric = string;
