"""Subscription lifecycle and credit note schemas — PDF A5 / B7."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from app.enums import CreditNoteReason, CreditNoteStatus, RecurringInterval
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class SubscriptionChangeRequest(ApiModel):
    """PDF A5/B7 — "mid cycle quantity or plan changes"."""

    new_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    new_interval: RecurringInterval | None = None
    #: Defaults to today. Must fall inside the period being changed.
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _needs_a_change(self) -> "SubscriptionChangeRequest":
        if self.new_quantity is None and self.new_interval is None:
            raise ValueError(
                "supply new_quantity and/or new_interval"
            )
        return self


class SubscriptionCancelRequest(ApiModel):
    """PDF A5/B7 — cancellation with partial refund."""

    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)


class SubscriptionSchedulePreview(ReadModel):
    schedule_number: str
    period_number: int
    status: str
    amount: Decimal
    period_start: date
    period_end: date


class SubscriptionChangeResponse(ReadModel):
    change_type: str
    sales_order_line_id: uuid.UUID
    effective_date: date
    periods_kept: int
    periods_regenerated: int
    previous_period_amount: Decimal
    new_period_amount: Decimal
    #: Amount credited back when the change reduces what was already billed.
    proration_credit: Decimal
    #: Amount additionally chargeable when the change increases the period.
    proration_charge: Decimal
    credit_note_id: uuid.UUID | None = None
    schedules: list[SubscriptionSchedulePreview] = Field(default_factory=list)
    #: Prose the UI can show verbatim; states the proration arithmetic.
    explanation: str


# ----------------------------------------------------------- credit notes
class CreditNoteRead(TimestampedRead):
    credit_note_number: str
    sales_order_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    billing_schedule_id: uuid.UUID | None = None
    customer_organization_id: uuid.UUID
    status: CreditNoteStatus
    reason: CreditNoteReason
    reason_note: str | None = None
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_refunded: Decimal
    amount_outstanding: Decimal
    issue_date: date
    issued_by_user_id: uuid.UUID | None = None
    voided_at: datetime | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class CreditNoteRefundRequest(ApiModel):
    #: Omit to refund the whole outstanding balance.
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )


class CreditNoteVoidRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)
