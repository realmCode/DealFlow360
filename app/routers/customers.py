"""Customer profile and contact endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.dependencies import DbSession, InternalUser, SalesUser
from app.enums import OrganizationKind
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.models.contact import Contact
from app.models.customer_profile import CustomerProfile
from app.models.organization import Organization
from app.schemas.customer import (
    ContactCreate,
    ContactRead,
    CustomerProfileCreate,
    CustomerProfileRead,
    CustomerProfileUpdate,
)
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/customers", tags=["customers"])


def _to_read(profile: CustomerProfile, org_name: str | None = None) -> CustomerProfileRead:
    return CustomerProfileRead(
        id=profile.id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        customer_organization_id=profile.customer_organization_id,
        customer_organization_name=org_name,
        display_name=profile.display_name,
        tier=profile.tier,
        payment_terms=profile.payment_terms,
        currency=profile.currency,
        credit_limit=profile.credit_limit,
        credit_used=profile.credit_used,
        credit_available=profile.credit_available,
        tax_rate_pct=profile.tax_rate_pct,
        is_active=profile.is_active,
    )


@router.post(
    "",
    response_model=CustomerProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer profile (and buyer organization if needed)",
)
async def create_customer(
    payload: CustomerProfileCreate, user: SalesUser, db: DbSession
) -> CustomerProfileRead:
    if payload.customer_organization_id is not None:
        buyer = await db.get(Organization, payload.customer_organization_id)
        if buyer is None:
            raise NotFoundError("Customer organization not found.")
        if buyer.kind is not OrganizationKind.CUSTOMER:
            raise BusinessRuleError(
                "The referenced organization is not a customer organization.",
                code="ORGANIZATION_NOT_CUSTOMER",
            )
    elif payload.customer_organization_name:
        buyer = await IdentityService.ensure_organization(
            db,
            name=payload.customer_organization_name,
            kind=OrganizationKind.CUSTOMER,
            currency=payload.currency,
        )
    else:
        raise BusinessRuleError(
            "Supply customer_organization_id or customer_organization_name.",
            code="CUSTOMER_ORGANIZATION_REQUIRED",
        )

    duplicate = (
        await db.execute(
            select(CustomerProfile).where(
                CustomerProfile.organization_id == user.organization_id,
                CustomerProfile.customer_organization_id == buyer.id,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError(
            "A customer profile already exists for that organization.",
            code="CUSTOMER_PROFILE_EXISTS",
            details={"customer_profile_id": str(duplicate.id)},
        )

    profile = CustomerProfile(
        organization_id=user.organization_id,
        customer_organization_id=buyer.id,
        display_name=payload.display_name,
        tier=payload.tier,
        payment_terms=payload.payment_terms,
        currency=payload.currency,
        credit_limit=payload.credit_limit,
        tax_rate_pct=payload.tax_rate_pct,
    )
    db.add(profile)
    await db.flush()

    for entry in payload.contacts:
        db.add(
            Contact(
                organization_id=user.organization_id,
                customer_organization_id=buyer.id,
                first_name=entry.first_name,
                last_name=entry.last_name,
                email=entry.email.strip().lower(),
                phone=entry.phone,
                title=entry.title,
                is_primary=entry.is_primary,
            )
        )
    await db.flush()
    await db.commit()
    return _to_read(profile, buyer.name)


@router.get("", response_model=list[CustomerProfileRead], summary="List customers")
async def list_customers(user: InternalUser, db: DbSession) -> list[CustomerProfileRead]:
    rows = (
        await db.execute(
            select(CustomerProfile, Organization)
            .join(Organization, Organization.id == CustomerProfile.customer_organization_id)
            .where(CustomerProfile.organization_id == user.organization_id)
            .order_by(CustomerProfile.display_name)
        )
    ).all()
    return [_to_read(profile, org.name) for profile, org in rows]


@router.get(
    "/{customer_id}", response_model=CustomerProfileRead, summary="Get one customer"
)
async def get_customer(
    customer_id: uuid.UUID, user: InternalUser, db: DbSession
) -> CustomerProfileRead:
    profile = await db.get(CustomerProfile, customer_id)
    if profile is None or profile.organization_id != user.organization_id:
        raise NotFoundError("Customer not found.")
    org = await db.get(Organization, profile.customer_organization_id)
    return _to_read(profile, org.name if org else None)


@router.patch(
    "/{customer_id}", response_model=CustomerProfileRead, summary="Update a customer"
)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerProfileUpdate,
    user: SalesUser,
    db: DbSession,
) -> CustomerProfileRead:
    profile = await db.get(CustomerProfile, customer_id)
    if profile is None or profile.organization_id != user.organization_id:
        raise NotFoundError("Customer not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(profile, key, value)
    await db.flush()
    await db.commit()
    org = await db.get(Organization, profile.customer_organization_id)
    return _to_read(profile, org.name if org else None)


@router.get(
    "/{customer_id}/contacts",
    response_model=list[ContactRead],
    summary="List contacts for a customer",
)
async def list_contacts(
    customer_id: uuid.UUID, user: InternalUser, db: DbSession
) -> list[ContactRead]:
    profile = await db.get(CustomerProfile, customer_id)
    if profile is None or profile.organization_id != user.organization_id:
        raise NotFoundError("Customer not found.")
    rows = (
        await db.execute(
            select(Contact)
            .where(
                Contact.organization_id == user.organization_id,
                Contact.customer_organization_id == profile.customer_organization_id,
            )
            .order_by(Contact.is_primary.desc(), Contact.email)
        )
    ).scalars()
    return [ContactRead.model_validate(c) for c in rows]


@router.post(
    "/{customer_id}/contacts",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a contact to a customer",
)
async def add_contact(
    customer_id: uuid.UUID,
    payload: ContactCreate,
    user: SalesUser,
    db: DbSession,
) -> ContactRead:
    profile = await db.get(CustomerProfile, customer_id)
    if profile is None or profile.organization_id != user.organization_id:
        raise NotFoundError("Customer not found.")
    contact = Contact(
        organization_id=user.organization_id,
        customer_organization_id=profile.customer_organization_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email.strip().lower(),
        phone=payload.phone,
        title=payload.title,
        is_primary=payload.is_primary,
    )
    db.add(contact)
    await db.flush()
    await db.commit()
    return ContactRead.model_validate(contact)
