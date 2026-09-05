"""Billing schedule, invoice and payment schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.enums import (
    BillingScheduleStatus,
    BillingType,
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
    RecurringInterval,
)
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class BillingScheduleRead(TimestampedRead):
    schedule_number: str
    sales_order_id: uuid.UUID
    sales_order_line_id: uuid.UUID | None = None
    billing_type: BillingType
    recurring_interval: RecurringInterval | None = None
    status: BillingScheduleStatus
    currency: str
    amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    period_number: int
    total_periods: int
    period_start: date
    period_end: date
    due_date: date
    is_prorated: bool
    proration_factor: Decimal
    description: str
    detail: dict[str, Any] = Field(default_factory=dict)


class BillingSummary(ReadModel):
    sales_order_id: uuid.UUID
    one_time_total: Decimal
    recurring_total_per_year: Decimal
    recurring_contract_total: Decimal
    grand_total: Decimal
    schedule_count: int
    one_time_count: Decimal
    recurring_count: Decimal


class InvoiceCreate(ApiModel):
    billing_schedule_id: uuid.UUID
    issue_date: date | None = None


class InvoiceRead(TimestampedRead):
    invoice_number: str
    sales_order_id: uuid.UUID
    billing_schedule_id: uuid.UUID | None = None
    status: InvoiceStatus
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    amount_due: Decimal
    issue_date: date
    due_date: date
    paid_at: datetime | None = None


class PaymentCreate(ApiModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    reference: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class PaymentRead(TimestampedRead):
    payment_number: str
    invoice_id: uuid.UUID
    amount: Decimal
    currency: str
    method: PaymentMethod
    status: PaymentStatus
    reference: str | None = None
    received_at: datetime


class ProrationPreview(ReadModel):
    """Reusable proration maths, exposed for UI previews and tests."""

    full_period_amount: Decimal
    days_in_period: int
    days_billed: int
    proration_factor: Decimal
    prorated_amount: Decimal
    explanation: str
