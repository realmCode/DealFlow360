"""Deal schemas."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import Field

from app.enums import CustomerTier, DealStage
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class DealCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    customer_profile_id: uuid.UUID
    reference: str | None = Field(default=None, max_length=64)
    stage: DealStage = DealStage.QUALIFICATION
    expected_value: Decimal = Field(default=Decimal("0"), ge=0)
    expected_close_date: date | None = None
    primary_contact_id: uuid.UUID | None = None
    notes: str | None = None


class DealUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    stage: DealStage | None = None
    expected_value: Decimal | None = Field(default=None, ge=0)
    expected_close_date: date | None = None
    notes: str | None = None


class DealQuoteSummary(ReadModel):
    id: uuid.UUID
    quote_number: str
    title: str
    status: str
    current_version_number: int


class DealRead(TimestampedRead):
    reference: str
    name: str
    customer_profile_id: uuid.UUID
    customer_display_name: str | None = None
    customer_tier: CustomerTier | None = None
    owner_user_id: uuid.UUID
    primary_contact_id: uuid.UUID | None = None
    stage: DealStage
    currency: str
    expected_value: Decimal
    expected_close_date: date | None = None
    notes: str | None = None
    quotes: list[DealQuoteSummary] = Field(default_factory=list)
