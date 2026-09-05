"""Domain enumerations shared by models, schemas and services.

All of these are persisted as ``VARCHAR`` with a database CHECK constraint
(``native_enum=False``) rather than PostgreSQL ENUM types: the values stay
readable in psql, and adding a value never needs an ``ALTER TYPE`` migration.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import sqlalchemy as sa


def enum_col(enum_cls: type[StrEnum], *, length: int = 48) -> sa.Enum:
    """VARCHAR + CHECK constraint backed by a Python StrEnum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],  # type: ignore[union-attr]
        name=f"ck_{enum_cls.__name__.lower()}",
    )


# ------------------------------------------------------------------ identity
class OrganizationKind(StrEnum):
    SELLER = "SELLER"
    CUSTOMER = "CUSTOMER"


class RoleCode(StrEnum):
    SALES = "SALES"
    MANAGER = "MANAGER"
    FINANCE = "FINANCE"
    OPS = "OPS"
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"


#: Roles that belong to the selling organization and may use internal APIs.
INTERNAL_ROLES: frozenset[RoleCode] = frozenset(
    {RoleCode.SALES, RoleCode.MANAGER, RoleCode.FINANCE, RoleCode.OPS, RoleCode.ADMIN}
)

#: Roles that may only use the customer portal.
EXTERNAL_ROLES: frozenset[RoleCode] = frozenset({RoleCode.CUSTOMER})


# ---------------------------------------------------------------- commercial
class CustomerTier(StrEnum):
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class PaymentTerms(StrEnum):
    PREPAID = "PREPAID"
    NET_15 = "NET_15"
    NET_30 = "NET_30"
    NET_45 = "NET_45"
    NET_60 = "NET_60"
    NET_90 = "NET_90"


class ProductCategory(StrEnum):
    HARDWARE = "HARDWARE"
    SOFTWARE = "SOFTWARE"
    SERVICE = "SERVICE"
    SUBSCRIPTION = "SUBSCRIPTION"


class BillingType(StrEnum):
    ONE_TIME = "ONE_TIME"
    RECURRING = "RECURRING"


class RecurringInterval(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


#: Months covered by one billing period of each interval.
INTERVAL_MONTHS: dict[RecurringInterval, int] = {
    RecurringInterval.MONTHLY: 1,
    RecurringInterval.QUARTERLY: 3,
    RecurringInterval.YEARLY: 12,
}


class DealStage(StrEnum):
    QUALIFICATION = "QUALIFICATION"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


# -------------------------------------------------------------------- quotes
class QuoteStatus(StrEnum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    LOST = "LOST"
    CANCELLED = "CANCELLED"


class QuoteVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    NEGOTIATING = "NEGOTIATING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


#: The only state in which quote lines may be mutated in place.
EDITABLE_VERSION_STATUSES: frozenset[QuoteVersionStatus] = frozenset(
    {QuoteVersionStatus.DRAFT}
)

#: States that can still be revised into a new version.
REVISABLE_VERSION_STATUSES: frozenset[QuoteVersionStatus] = frozenset(
    {
        QuoteVersionStatus.DRAFT,
        QuoteVersionStatus.PENDING_APPROVAL,
        QuoteVersionStatus.APPROVED,
        QuoteVersionStatus.SENT,
        QuoteVersionStatus.NEGOTIATING,
    }
)

#: Terminal states — immutable forever, cannot even be revised.
TERMINAL_VERSION_STATUSES: frozenset[QuoteVersionStatus] = frozenset(
    {
        QuoteVersionStatus.CONFIRMED,
        QuoteVersionStatus.REJECTED,
        QuoteVersionStatus.SUPERSEDED,
    }
)

#: Never exposed to a customer portal user: an unfinished internal draft.
CUSTOMER_HIDDEN_VERSION_STATUSES: frozenset[QuoteVersionStatus] = frozenset(
    {QuoteVersionStatus.DRAFT}
)

#: Versions a customer portal user may see, once the quote has been issued.
#: A version that is back under internal review is still shown — the customer
#: sees the terms they asked for plus "pending review", which is more honest
#: than hiding their own counter-offer — but never the reasoning behind it.
CUSTOMER_VISIBLE_VERSION_STATUSES: frozenset[QuoteVersionStatus] = frozenset(
    set(QuoteVersionStatus) - CUSTOMER_HIDDEN_VERSION_STATUSES
)


class QuoteVersionSource(StrEnum):
    INITIAL = "INITIAL"
    INTERNAL_REVISION = "INTERNAL_REVISION"
    CUSTOMER_COUNTER = "CUSTOMER_COUNTER"
    APPROVER_REVISION_REQUEST = "APPROVER_REVISION_REQUEST"


# ------------------------------------------------------------------ policies
class PolicyType(StrEnum):
    CATEGORY_DISCOUNT_CEILING = "CATEGORY_DISCOUNT_CEILING"
    MIN_MARGIN = "MIN_MARGIN"
    DISCOUNT_AMOUNT_AUTHORITY = "DISCOUNT_AMOUNT_AUTHORITY"
    PAYMENT_TERMS_LIMIT = "PAYMENT_TERMS_LIMIT"


class PolicyComparison(StrEnum):
    LTE = "LTE"  # actual must be <= threshold
    GTE = "GTE"  # actual must be >= threshold


class PolicyUnit(StrEnum):
    PERCENT = "PERCENT"
    AMOUNT = "AMOUNT"
    DAYS = "DAYS"


class PolicyResultStatus(StrEnum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    VIOLATED = "VIOLATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RiskBand(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ----------------------------------------------------------------- approvals
class ApprovalLevel(StrEnum):
    """Who must sign off. Ordered by escalation seniority."""

    SALES_MANAGER = "SALES_MANAGER"
    FINANCE = "FINANCE"
    EXECUTIVE = "EXECUTIVE"


#: Escalation order and the role that satisfies each level.
APPROVAL_LEVEL_ORDER: dict[ApprovalLevel, int] = {
    ApprovalLevel.SALES_MANAGER: 1,
    ApprovalLevel.FINANCE: 2,
    ApprovalLevel.EXECUTIVE: 3,
}

APPROVAL_LEVEL_ROLE: dict[ApprovalLevel, RoleCode] = {
    ApprovalLevel.SALES_MANAGER: RoleCode.MANAGER,
    ApprovalLevel.FINANCE: RoleCode.FINANCE,
    ApprovalLevel.EXECUTIVE: RoleCode.ADMIN,
}


class ApprovalRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    STALE = "STALE"
    CANCELLED = "CANCELLED"


class ApprovalStepStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    SKIPPED = "SKIPPED"
    STALE = "STALE"


class ApprovalDecisionType(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


# ---------------------------------------------------------------- attention
class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class AttentionItemType(StrEnum):
    STALE_APPROVAL = "STALE_APPROVAL"
    MARGIN_VIOLATION = "MARGIN_VIOLATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    INVENTORY_SHORTAGE = "INVENTORY_SHORTAGE"
    CUSTOMER_RESPONSE_REQUIRED = "CUSTOMER_RESPONSE_REQUIRED"
    ORDER_BLOCKED = "ORDER_BLOCKED"
    #: PDF B9.2 — a discount well above this rep's own historical average.
    #: Distinct from MARGIN_VIOLATION, which is an absolute policy breach:
    #: this fires on behavioural drift even when every ceiling is respected.
    DISCOUNT_ANOMALY = "DISCOUNT_ANOMALY"
    #: PDF B9.3 — promised delivery date is at risk or already missed.
    DELIVERY_SLIPPAGE = "DELIVERY_SLIPPAGE"
    #: PDF B9.1 — no customer movement for the configured window.
    STALLED_DEAL = "STALLED_DEAL"
    #: An approval step has waited beyond the configured SLA.
    APPROVAL_SLA_BREACH = "APPROVAL_SLA_BREACH"
    #: Stock has fallen to or below the warehouse reorder point (PDF A4.3).
    INVENTORY_REORDER_NEEDED = "INVENTORY_REORDER_NEEDED"


class AttentionItemStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


# -------------------------------------------------------------- negotiation
class NegotiationThreadStatus(StrEnum):
    OPEN = "OPEN"
    AWAITING_SELLER = "AWAITING_SELLER"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class NegotiationMessageType(StrEnum):
    COMMENT = "COMMENT"
    QUESTION = "QUESTION"
    CHANGE_REQUEST = "CHANGE_REQUEST"
    COUNTER_OFFER = "COUNTER_OFFER"
    SELLER_REPLY = "SELLER_REPLY"
    SYSTEM = "SYSTEM"


class AuthorKind(StrEnum):
    CUSTOMER = "CUSTOMER"
    SELLER = "SELLER"
    SYSTEM = "SYSTEM"


# ---------------------------------------------------------------- execution
class SalesOrderStatus(StrEnum):
    CREATED = "CREATED"
    ALLOCATED = "ALLOCATED"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    BACKORDERED = "BACKORDERED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class AllocationStatus(StrEnum):
    RESERVED = "RESERVED"
    ALLOCATED = "ALLOCATED"
    BACKORDERED = "BACKORDERED"
    SHIPPED = "SHIPPED"
    RELEASED = "RELEASED"
    CANCELLED = "CANCELLED"


class AllocationMode(StrEnum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class FulfillmentStatus(StrEnum):
    PENDING = "PENDING"
    PICKED = "PICKED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


# ------------------------------------------------------------------ billing
class BillingScheduleStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    INVOICED = "INVOICED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    VOID = "VOID"


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    CHECK = "CHECK"
    ACH = "ACH"
    OTHER = "OTHER"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class CreditNoteStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    #: Fully consumed — either refunded in cash or offset against billing.
    APPLIED = "APPLIED"
    VOID = "VOID"


class CreditNoteReason(StrEnum):
    SUBSCRIPTION_CANCELLED = "SUBSCRIPTION_CANCELLED"
    SUBSCRIPTION_DOWNGRADED = "SUBSCRIPTION_DOWNGRADED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    BILLING_CORRECTION = "BILLING_CORRECTION"
    GOODWILL = "GOODWILL"


class SubscriptionChangeType(StrEnum):
    QUANTITY = "QUANTITY"
    INTERVAL = "INTERVAL"
    CANCELLATION = "CANCELLATION"


# ------------------------------------------------------------------- system
class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


ALL_ENUMS: tuple[type[StrEnum], ...] = (
    OrganizationKind,
    RoleCode,
    CustomerTier,
    PaymentTerms,
    ProductCategory,
    BillingType,
    RecurringInterval,
    DealStage,
    QuoteStatus,
    QuoteVersionStatus,
    QuoteVersionSource,
    PolicyType,
    PolicyComparison,
    PolicyUnit,
    PolicyResultStatus,
    RiskBand,
    ApprovalLevel,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalDecisionType,
    Severity,
    AttentionItemType,
    AttentionItemStatus,
    NegotiationThreadStatus,
    NegotiationMessageType,
    AuthorKind,
    SalesOrderStatus,
    AllocationStatus,
    AllocationMode,
    FulfillmentStatus,
    BillingScheduleStatus,
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
    CreditNoteStatus,
    CreditNoteReason,
    SubscriptionChangeType,
    IdempotencyStatus,
)


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [m.value for m in enum_cls]


def as_json(value: Any) -> Any:
    """Coerce enum members to their string value for JSONB payloads."""
    if isinstance(value, StrEnum):
        return value.value
    return value
