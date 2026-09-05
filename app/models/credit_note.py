"""Table 37 — credit_notes.

PDF A5 requires "cancellation and partial refund rules" and B7 requires
"an automatic partial refund or credit note trigger when applicable". Neither
was representable: `BillingScheduleStatus.CANCELLED` and
`PaymentStatus.REFUNDED` both existed in the enums with no code path reaching
them, and there was no entity to record the credit itself.

A credit note is issued rather than an invoice being edited, because an issued
invoice is a financial record: reducing it in place would destroy the audit
trail of what the customer was originally billed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import CreditNoteReason, CreditNoteStatus, enum_col
from app.models.base import (
    Base,
    JsonDict,
    LongText,
    Money,
    OrgOwnedMixin,
    Str64,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class CreditNote(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    __tablename__ = "credit_notes"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "credit_note_number",
            name="uq_credit_notes_organization_id_credit_note_number",
        ),
        sa.CheckConstraint("subtotal >= 0", name="subtotal_non_negative"),
        sa.CheckConstraint("tax_amount >= 0", name="tax_amount_non_negative"),
        sa.CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
        sa.CheckConstraint(
            "amount_refunded >= 0 AND amount_refunded <= total_amount",
            name="amount_refunded_within_total",
        ),
        sa.Index("ix_credit_notes_organization_id_status", "organization_id", "status"),
        sa.Index("ix_credit_notes_sales_order_id", "sales_order_id"),
    )

    credit_note_number: Mapped[Str64] = mapped_column(nullable=False)

    #: RESTRICT: a credit note is a financial record and must outlive
    #: convenience deletions of the order it relates to.
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The invoice being credited. Null when the cancelled periods were never
    #: invoiced — the credit then exists purely as a record of the adjustment.
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    billing_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("billing_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[CreditNoteStatus] = mapped_column(
        enum_col(CreditNoteStatus), nullable=False, default=CreditNoteStatus.ISSUED
    )
    reason: Mapped[CreditNoteReason] = mapped_column(
        enum_col(CreditNoteReason), nullable=False
    )
    reason_note: Mapped[LongText | None] = mapped_column(nullable=True)

    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    subtotal: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    total_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    #: How much of this credit has actually been paid back in cash, as opposed
    #: to being held as a credit against future billing.
    amount_refunded: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0")
    )

    issue_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    #: The proration arithmetic that produced `total_amount`, so a customer
    #: dispute can be answered without re-deriving it.
    detail: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)

    @property
    def amount_outstanding(self) -> Decimal:
        return Decimal(self.total_amount) - Decimal(self.amount_refunded)
