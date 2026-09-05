"""Negotiation / customer-portal message schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from app.enums import AuthorKind, NegotiationMessageType, NegotiationThreadStatus
from app.schemas.common import ApiModel, ReadModel


class CounterOfferLine(ApiModel):
    quote_line_id: uuid.UUID
    requested_discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    requested_quantity: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _needs_a_request(self) -> "CounterOfferLine":
        if self.requested_discount_pct is None and self.requested_quantity is None:
            raise ValueError(
                "a counter-offer line must request a discount and/or a quantity"
            )
        return self


class PortalMessageCreate(ApiModel):
    """One endpoint covers comments, questions and counter-offers.

    ``COUNTER_OFFER`` and ``CHANGE_REQUEST`` require ``lines`` and trigger the
    revision + Decision Fabric flow. Everything else is conversation only.
    """

    message_type: NegotiationMessageType = NegotiationMessageType.COMMENT
    body: str = Field(min_length=1, max_length=4000)
    quote_line_id: uuid.UUID | None = None
    lines: list[CounterOfferLine] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape(self) -> "PortalMessageCreate":
        if self.message_type in (
            NegotiationMessageType.COUNTER_OFFER,
            NegotiationMessageType.CHANGE_REQUEST,
        ):
            if not self.lines:
                raise ValueError(
                    f"{self.message_type.value} requires at least one entry in 'lines'"
                )
        elif self.lines:
            raise ValueError(
                "'lines' may only be supplied for COUNTER_OFFER or CHANGE_REQUEST"
            )
        if self.message_type in (
            NegotiationMessageType.SELLER_REPLY,
            NegotiationMessageType.SYSTEM,
        ):
            raise ValueError(
                "customers may not post SELLER_REPLY or SYSTEM messages"
            )
        return self


class NegotiationMessageRead(ReadModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    quote_version_id: uuid.UUID
    quote_line_id: uuid.UUID | None = None
    author_kind: AuthorKind
    author_display_name: str
    message_type: NegotiationMessageType
    body: str
    requested_discount_pct: Decimal | None = None
    requested_quantity: Decimal | None = None
    requested_unit_price: Decimal | None = None
    triggered_version_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class NegotiationThreadRead(ReadModel):
    id: uuid.UUID
    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    subject: str
    status: NegotiationThreadStatus
    message_count: int
    last_message_at: datetime | None = None
    messages: list[NegotiationMessageRead] = Field(default_factory=list)


class CounterOfferOutcome(ReadModel):
    """What the portal shows the customer after they counter."""

    message: NegotiationMessageRead
    new_version_id: uuid.UUID | None = None
    new_version_number: int | None = None
    status: str
    requires_reapproval: bool
    #: Customer-safe summary. Never includes cost, margin or policy internals.
    customer_message: str


class ConfirmRequest(ApiModel):
    acceptance_note: str | None = Field(default=None, max_length=2000)
