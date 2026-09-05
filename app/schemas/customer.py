"""Customer profile and contact schemas."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import EmailStr, Field

from app.enums import CustomerTier, PaymentTerms
from app.schemas.common import ApiModel, TimestampedRead


class ContactCreate(ApiModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    title: str | None = Field(default=None, max_length=128)
    is_primary: bool = False


class ContactRead(TimestampedRead):
    customer_organization_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    first_name: str
    last_name: str | None = None
    email: str
    phone: str | None = None
    title: str | None = None
    is_primary: bool
    is_active: bool


class CustomerProfileCreate(ApiModel):
    """Creates the buyer organization on the fly when no id is supplied."""

    customer_organization_id: uuid.UUID | None = None
    customer_organization_name: str | None = Field(default=None, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    tier: CustomerTier = CustomerTier.BRONZE
    payment_terms: PaymentTerms = PaymentTerms.NET_30
    currency: str = Field(default="USD", min_length=3, max_length=3)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    contacts: list[ContactCreate] = Field(default_factory=list)


class CustomerProfileUpdate(ApiModel):
    display_name: str | None = Field(default=None, max_length=255)
    tier: CustomerTier | None = None
    payment_terms: PaymentTerms | None = None
    credit_limit: Decimal | None = Field(default=None, ge=0)
    tax_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


class CustomerProfileRead(TimestampedRead):
    customer_organization_id: uuid.UUID
    customer_organization_name: str | None = None
    display_name: str
    tier: CustomerTier
    payment_terms: PaymentTerms
    currency: str
    credit_limit: Decimal
    credit_used: Decimal
    credit_available: Decimal
    tax_rate_pct: Decimal
    is_active: bool
