"""All 38 ORM models.

Importing this package registers every table on ``Base.metadata``, which is
what Alembic autogenerate and the DB verification script both rely on.
"""

from __future__ import annotations

from app.models.approval_decision import ApprovalDecision
from app.models.approval_request import ApprovalRequest
from app.models.approval_step import ApprovalStep
from app.models.attention_item import AttentionItem
from app.models.audit_event import AuditEvent
from app.models.base import Base
from app.models.billing_schedule import BillingSchedule
from app.models.commercial_snapshot import CommercialSnapshot
from app.models.contact import Contact
from app.models.credit_note import CreditNote
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.decision_impact import DecisionImpact
from app.models.dismissed_recommendation import DismissedRecommendation
from app.models.fulfillment import Fulfillment
from app.models.idempotency_key import IdempotencyKey
from app.models.inventory import Inventory
from app.models.inventory_allocation import InventoryAllocation
from app.models.invoice import Invoice
from app.models.negotiation_message import NegotiationMessage
from app.models.negotiation_thread import NegotiationThread
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettings
from app.models.payment import Payment
from app.models.policy import Policy
from app.models.policy_result import PolicyResult
from app.models.product import PriceList, Product, ProductVariant
from app.models.quote import Quote
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.models.role import Role
from app.models.sales_order import SalesOrder
from app.models.sales_order_line import SalesOrderLine
from app.models.sales_team import SalesTeam, SalesTeamMember
from app.models.user import User
from app.models.warehouse import Warehouse

#: Canonical table inventory — asserted by tests and scripts/verify_db.py.
EXPECTED_TABLES: tuple[str, ...] = (
    # identity (4)
    "organizations",
    "roles",
    "users",
    "contacts",
    # commercial (5)
    "customer_profiles",
    "products",
    "product_variants",
    "price_lists",
    "deals",
    # quotes (3)
    "quotes",
    "quote_versions",
    "quote_lines",
    # decision fabric (3)
    "policies",
    "policy_results",
    "commercial_snapshots",
    # approvals (3)
    "approval_requests",
    "approval_steps",
    "approval_decisions",
    # decision tracking (2)
    "decision_impacts",
    "attention_items",
    # negotiation (2)
    "negotiation_threads",
    "negotiation_messages",
    # execution (3)
    "sales_orders",
    "sales_order_lines",
    "fulfillments",
    # inventory (3)
    "warehouses",
    "inventory",
    "inventory_allocations",
    # billing (4)
    "billing_schedules",
    "invoices",
    "payments",
    "credit_notes",
    # configuration and reporting (3)
    "organization_settings",
    "sales_teams",
    "sales_team_members",
    # recommendations (1)
    "dismissed_recommendations",
    # system (2)
    "audit_events",
    "idempotency_keys",
)

__all__ = [
    "Base",
    "EXPECTED_TABLES",
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStep",
    "AttentionItem",
    "AuditEvent",
    "BillingSchedule",
    "CommercialSnapshot",
    "Contact",
    "CreditNote",
    "CustomerProfile",
    "Deal",
    "DecisionImpact",
    "DismissedRecommendation",
    "Fulfillment",
    "IdempotencyKey",
    "Inventory",
    "InventoryAllocation",
    "Invoice",
    "NegotiationMessage",
    "NegotiationThread",
    "Organization",
    "OrganizationSettings",
    "Payment",
    "PriceList",
    "Policy",
    "PolicyResult",
    "Product",
    "ProductVariant",
    "Quote",
    "QuoteLine",
    "QuoteVersion",
    "Role",
    "SalesOrder",
    "SalesOrderLine",
    "SalesTeam",
    "SalesTeamMember",
    "User",
    "Warehouse",
]
