"""Canonical deterministic seed data.

Properties this script guarantees:

* **Deterministic** — same inputs every run; no randomness, no timestamps in
  business keys.
* **Idempotent** — every entity is looked up by its natural key first. Running
  it twice produces the same row count and mutates nothing.
* **Transactional** — the CLI wraps the whole load in one transaction; the
  ``POST /admin/seed`` endpoint joins the request's transaction.

Usage:
    python -m scripts.seed              # load into DATABASE_URL
    ENVIRONMENT=test python -m scripts.seed
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import dispose_engine, get_sessionmaker
from app.enums import (
    ApprovalLevel,
    BillingType,
    CustomerTier,
    OrganizationKind,
    PaymentTerms,
    PolicyComparison,
    PolicyType,
    PolicyUnit,
    ProductCategory,
    RecurringInterval,
    RoleCode,
    Severity,
)
from app.models.contact import Contact
from app.models.customer_profile import CustomerProfile
from app.models.inventory import Inventory
from app.models.organization import Organization
from app.models.policy import Policy
from app.models.product import Product
from app.models.role import Role
from app.models.sales_team import SalesTeam
from app.models.warehouse import Warehouse
from app.services.identity_service import IdentityService
from app.services.inventory_service import InventoryService
from app.services.sales_team_service import SalesTeamService
from app.services.settings_service import SettingsService

SELLER_NAME = "TechSupply Solutions"
SELLER_SLUG = "techsupply-solutions"
CUSTOMER_NAME = "Acme Corporation"
CUSTOMER_SLUG = "acme-corporation"

#: Demo credentials. Documented in README; never use these outside a demo.
SEED_USERS: tuple[tuple[str, str, RoleCode, str], ...] = (
    ("sales@techsupply.com", "Sam Rivera", RoleCode.SALES, "seller"),
    ("manager@techsupply.com", "Morgan Chen", RoleCode.MANAGER, "seller"),
    ("finance@techsupply.com", "Fran Delgado", RoleCode.FINANCE, "seller"),
    ("ops@techsupply.com", "Omar Petrov", RoleCode.OPS, "seller"),
    ("admin@techsupply.com", "Avery Stone", RoleCode.ADMIN, "seller"),
    ("customer@acme.com", "Casey Nolan", RoleCode.CUSTOMER, "customer"),
)

SEED_PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "sku": "HW-LAPTOP-01",
        "name": "Business Laptop",
        "description": "14-inch business laptop, 16GB RAM, 512GB SSD.",
        "category": ProductCategory.HARDWARE,
        "list_price": Decimal("1200.0000"),
        "internal_cost": Decimal("800.0000"),
        "billing_type": BillingType.ONE_TIME,
        "is_stock_tracked": True,
    },
    {
        "sku": "HW-MONITOR-27",
        "name": '27" Monitor',
        "description": "27-inch QHD IPS monitor with USB-C docking.",
        "category": ProductCategory.HARDWARE,
        "list_price": Decimal("400.0000"),
        "internal_cost": Decimal("200.0000"),
        "billing_type": BillingType.ONE_TIME,
        "is_stock_tracked": True,
    },
    {
        "sku": "SV-INSTALL-01",
        "name": "Installation Service",
        "description": "On-site deployment, imaging and handover.",
        "category": ProductCategory.SERVICE,
        "list_price": Decimal("500.0000"),
        "internal_cost": Decimal("150.0000"),
        "billing_type": BillingType.ONE_TIME,
        "is_stock_tracked": False,
    },
    {
        "sku": "SB-SUPPORT-01",
        "name": "Annual Support Plan",
        "description": "24/7 support and next-business-day hardware replacement.",
        "category": ProductCategory.SUBSCRIPTION,
        "list_price": Decimal("300.0000"),
        "internal_cost": Decimal("50.0000"),
        "billing_type": BillingType.RECURRING,
        "recurring_interval": RecurringInterval.YEARLY,
        "default_recurring_periods": 1,
        "is_stock_tracked": False,
    },
)

SEED_WAREHOUSES: tuple[dict[str, Any], ...] = (
    {
        "code": "MAIN",
        "name": "Main Warehouse",
        "region": "West",
        "city": "San Jose",
        "country": "US",
        "priority": 10,
        "shipping_cost_per_shipment": Decimal("120.00"),
    },
    {
        "code": "EAST",
        "name": "East Depot",
        "region": "East",
        "city": "Newark",
        "country": "US",
        "priority": 20,
        "shipping_cost_per_shipment": Decimal("180.00"),
    },
)

#: Canonical stock: 60 laptops at Main, 40 at East Depot.
SEED_STOCK: tuple[tuple[str, str, Decimal], ...] = (
    ("MAIN", "HW-LAPTOP-01", Decimal("60")),
    ("EAST", "HW-LAPTOP-01", Decimal("40")),
    ("MAIN", "HW-MONITOR-27", Decimal("150")),
    ("EAST", "HW-MONITOR-27", Decimal("50")),
)

SEED_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "code": "GOLD-HW-CEILING",
        "name": "Gold tier hardware discount ceiling",
        "description": (
            "Gold customers may receive up to 15% off hardware without escalation. "
            "Anything above requires Sales Manager sign-off."
        ),
        "policy_type": PolicyType.CATEGORY_DISCOUNT_CEILING,
        "customer_tier": CustomerTier.GOLD,
        "product_category": ProductCategory.HARDWARE,
        "threshold_value": Decimal("15.0000"),
        "comparison": PolicyComparison.LTE,
        "unit": PolicyUnit.PERCENT,
        "required_action": ApprovalLevel.SALES_MANAGER,
        "severity": Severity.MEDIUM,
        "priority": 10,
    },
    {
        "code": "GOLD-SV-CEILING",
        "name": "Gold tier service discount ceiling",
        "description": (
            "Services carry far less room than hardware: Gold customers may "
            "receive up to 10% off, above which a Sales Manager must approve."
        ),
        "policy_type": PolicyType.CATEGORY_DISCOUNT_CEILING,
        "customer_tier": CustomerTier.GOLD,
        "product_category": ProductCategory.SERVICE,
        "threshold_value": Decimal("10.0000"),
        "comparison": PolicyComparison.LTE,
        "unit": PolicyUnit.PERCENT,
        "required_action": ApprovalLevel.SALES_MANAGER,
        "severity": Severity.MEDIUM,
        "priority": 10,
    },
    {
        "code": "GOLD-SB-CEILING",
        "name": "Gold tier subscription discount ceiling",
        "description": "Subscriptions may be discounted up to 10% for Gold customers.",
        "policy_type": PolicyType.CATEGORY_DISCOUNT_CEILING,
        "customer_tier": CustomerTier.GOLD,
        "product_category": ProductCategory.SUBSCRIPTION,
        "threshold_value": Decimal("10.0000"),
        "comparison": PolicyComparison.LTE,
        "unit": PolicyUnit.PERCENT,
        "required_action": ApprovalLevel.SALES_MANAGER,
        "severity": Severity.MEDIUM,
        "priority": 10,
    },
    {
        "code": "STD-HW-CEILING",
        "name": "Standard hardware discount ceiling",
        "description": (
            "Fallback ceiling for any tier without a specific rule. Applies to "
            "hardware only."
        ),
        "policy_type": PolicyType.CATEGORY_DISCOUNT_CEILING,
        "customer_tier": None,
        "product_category": ProductCategory.HARDWARE,
        "threshold_value": Decimal("10.0000"),
        "comparison": PolicyComparison.LTE,
        "unit": PolicyUnit.PERCENT,
        "required_action": ApprovalLevel.SALES_MANAGER,
        "severity": Severity.MEDIUM,
        "priority": 900,
    },
    {
        "code": "MIN-MARGIN-10",
        "name": "Minimum blended margin 10%",
        "description": (
            "No quote may be issued below 10% blended margin without Finance "
            "sign-off, regardless of tier."
        ),
        "policy_type": PolicyType.MIN_MARGIN,
        "customer_tier": None,
        "product_category": None,
        "threshold_value": Decimal("10.0000"),
        "comparison": PolicyComparison.GTE,
        "unit": PolicyUnit.PERCENT,
        "required_action": ApprovalLevel.FINANCE,
        "severity": Severity.HIGH,
        "priority": 10,
    },
    {
        "code": "DISCOUNT-AUTHORITY-20K",
        "name": "Discount signing authority 20,000",
        "description": (
            "A Sales Manager may sign off up to 20,000 of total discount. Beyond "
            "that the give-away needs Finance authority, independent of margin."
        ),
        "policy_type": PolicyType.DISCOUNT_AMOUNT_AUTHORITY,
        "customer_tier": None,
        "product_category": None,
        "threshold_value": Decimal("20000.0000"),
        "comparison": PolicyComparison.LTE,
        "unit": PolicyUnit.AMOUNT,
        "required_action": ApprovalLevel.FINANCE,
        "severity": Severity.HIGH,
        "priority": 20,
    },
    {
        # The PAYMENT_TERMS_LIMIT evaluator was fully implemented and never
        # fired, because nothing seeded a policy of this type. One row makes a
        # fourth policy type demonstrable at no code cost.
        "code": "GOLD-TERMS-60",
        "name": "Gold tier payment terms limit",
        "description": (
            "Gold customers may be granted up to 60 days to pay. Anything "
            "longer is a working-capital decision for Finance."
        ),
        "policy_type": PolicyType.PAYMENT_TERMS_LIMIT,
        "customer_tier": CustomerTier.GOLD,
        "product_category": None,
        "threshold_value": Decimal("60.0000"),
        "comparison": PolicyComparison.LTE,
        "unit": PolicyUnit.DAYS,
        "required_action": ApprovalLevel.FINANCE,
        "severity": Severity.MEDIUM,
        "priority": 30,
    },
)

#: PDF A7.4 — reports filter by "Sales Team / Rep", so the demo needs a team.
SEED_TEAMS: tuple[dict[str, Any], ...] = (
    {
        "code": "WEST",
        "name": "West Enterprise",
        "description": "Enterprise accounts west of the Rockies.",
        "region": "West",
        "manager_email": "manager@techsupply.com",
        "member_emails": ("sales@techsupply.com", "manager@techsupply.com"),
    },
)

#: PDF A6.2 — a promoted product so the upsell panel can show its tag.
SEED_PROMOTED_SKUS: tuple[str, ...] = ("SB-SUPPORT-01",)


async def seed_canonical_data(session: AsyncSession) -> dict[str, Any]:
    """Idempotently load the canonical demo dataset. Does not commit."""
    created: dict[str, int] = {
        "roles": 0,
        "organizations": 0,
        "users": 0,
        "customer_profiles": 0,
        "contacts": 0,
        "products": 0,
        "warehouses": 0,
        "inventory": 0,
        "policies": 0,
        "sales_teams": 0,
    }

    # ------------------------------------------------------------- roles
    before = len((await session.execute(select(Role.id))).scalars().all())
    roles = await IdentityService.ensure_roles(session)
    created["roles"] = max(0, len(roles) - before)

    # ----------------------------------------------------- organizations
    seller = (
        await session.execute(
            select(Organization).where(Organization.slug == SELLER_SLUG)
        )
    ).scalar_one_or_none()
    if seller is None:
        seller = await IdentityService.ensure_organization(
            session,
            name=SELLER_NAME,
            kind=OrganizationKind.SELLER,
            slug=SELLER_SLUG,
            domain="techsupply.com",
        )
        created["organizations"] += 1

    buyer = (
        await session.execute(
            select(Organization).where(Organization.slug == CUSTOMER_SLUG)
        )
    ).scalar_one_or_none()
    if buyer is None:
        buyer = await IdentityService.ensure_organization(
            session,
            name=CUSTOMER_NAME,
            kind=OrganizationKind.CUSTOMER,
            slug=CUSTOMER_SLUG,
            domain="acme.com",
        )
        created["organizations"] += 1

    # ------------------------------------------------------------- users
    for email, full_name, role_code, side in SEED_USERS:
        existing = await IdentityService.by_email(session, email)
        if existing is not None:
            continue
        await IdentityService.create_user(
            session,
            email=email,
            password=settings.seed_default_password,
            full_name=full_name,
            role_code=role_code,
            organization=seller if side == "seller" else buyer,
        )
        created["users"] += 1

    # -------------------------------------------------- customer profile
    profile = (
        await session.execute(
            select(CustomerProfile).where(
                CustomerProfile.organization_id == seller.id,
                CustomerProfile.customer_organization_id == buyer.id,
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = CustomerProfile(
            organization_id=seller.id,
            customer_organization_id=buyer.id,
            display_name=CUSTOMER_NAME,
            tier=CustomerTier.GOLD,
            payment_terms=PaymentTerms.NET_30,
            currency="USD",
            credit_limit=Decimal("500000.00"),
            tax_rate_pct=Decimal("0.0000"),
        )
        session.add(profile)
        await session.flush()
        created["customer_profiles"] += 1

    portal_user = await IdentityService.by_email(session, "customer@acme.com")
    contact = (
        await session.execute(
            select(Contact).where(
                Contact.organization_id == seller.id,
                Contact.email == "customer@acme.com",
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        contact = Contact(
            organization_id=seller.id,
            customer_organization_id=buyer.id,
            user_id=portal_user.id if portal_user else None,
            first_name="Casey",
            last_name="Nolan",
            email="customer@acme.com",
            title="Head of IT Procurement",
            is_primary=True,
        )
        session.add(contact)
        await session.flush()
        created["contacts"] += 1
    if profile.primary_contact_id is None:
        profile.primary_contact_id = contact.id
        await session.flush()

    # ---------------------------------------------------------- products
    products: dict[str, Product] = {}
    for spec in SEED_PRODUCTS:
        existing = (
            await session.execute(
                select(Product).where(
                    Product.organization_id == seller.id, Product.sku == spec["sku"]
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = Product(organization_id=seller.id, **spec)
            session.add(existing)
            await session.flush()
            created["products"] += 1
        products[spec["sku"]] = existing

    # -------------------------------------------------------- warehouses
    warehouses: dict[str, Warehouse] = {}
    for spec in SEED_WAREHOUSES:
        existing = (
            await session.execute(
                select(Warehouse).where(
                    Warehouse.organization_id == seller.id,
                    Warehouse.code == spec["code"],
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = Warehouse(organization_id=seller.id, **spec)
            session.add(existing)
            await session.flush()
            created["warehouses"] += 1
        warehouses[spec["code"]] = existing

    # ------------------------------------------------------------- stock
    for wh_code, sku, quantity in SEED_STOCK:
        warehouse = warehouses[wh_code]
        product = products[sku]
        existing = (
            await session.execute(
                select(Inventory).where(
                    Inventory.warehouse_id == warehouse.id,
                    Inventory.product_id == product.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            # Re-running the seed must not disturb live reservations.
            continue
        await InventoryService.upsert_stock(
            session,
            organization_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity_on_hand=quantity,
            reorder_point=Decimal("10"),
        )
        created["inventory"] += 1

    # ---------------------------------------------------------- policies
    for spec in SEED_POLICIES:
        existing = (
            await session.execute(
                select(Policy).where(
                    Policy.organization_id == seller.id, Policy.code == spec["code"]
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(Policy(organization_id=seller.id, **spec))
            await session.flush()
            created["policies"] += 1

    # ------------------------------------------------- promoted products
    for sku in SEED_PROMOTED_SKUS:
        product = products.get(sku)
        if product is not None and not product.is_promoted:
            product.is_promoted = True
            await session.flush()

    # -------------------------------------------------- governance settings
    # Materialise the row so the demo can show it being edited rather than
    # created; SettingsService would otherwise create it on first read.
    await SettingsService.for_org(session, seller.id)

    # ------------------------------------------------------- sales teams
    for spec in SEED_TEAMS:
        existing = (
            await session.execute(
                select(SalesTeam).where(
                    SalesTeam.organization_id == seller.id,
                    SalesTeam.code == spec["code"],
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        manager = await IdentityService.by_email(session, spec["manager_email"])
        members = []
        for email in spec["member_emails"]:
            member = await IdentityService.by_email(session, email)
            if member is not None:
                members.append(member.id)
        await SalesTeamService.create(
            session,
            organization_id=seller.id,
            code=spec["code"],
            name=spec["name"],
            description=spec["description"],
            manager_user_id=manager.id if manager else None,
            region=spec["region"],
            member_user_ids=members,
        )
        created["sales_teams"] += 1

    return {
        "status": "ok",
        "seller_organization_id": str(seller.id),
        "customer_organization_id": str(buyer.id),
        "customer_profile_id": str(profile.id),
        "created": created,
        "idempotent": all(v == 0 for v in created.values()),
        "demo_password": settings.seed_default_password,
        "users": [email for email, _n, _r, _s in SEED_USERS],
        "products": {sku: str(p.id) for sku, p in products.items()},
        "warehouses": {code: str(w.id) for code, w in warehouses.items()},
    }


async def main() -> int:
    print("=" * 62)
    print("DEALFLOW360 SEED")
    print(f"target: {settings.active_database_url.split('@')[-1]}")
    print("=" * 62)

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await seed_canonical_data(session)
        await session.commit()

    await dispose_engine()

    created = result["created"]
    total = sum(created.values())
    for entity, count in created.items():
        marker = "+" if count else "="
        print(f"  {marker} {entity:20s} {count}")
    print("-" * 62)
    if total == 0:
        print("Nothing created — data already present (seed is idempotent).")
    else:
        print(f"Created {total} row(s).")
    print(f"Demo password for all seed users: {result['demo_password']}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
