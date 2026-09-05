"""Table 31/33 — payments."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import PaymentMethod, PaymentStatus, enum_col
from app.models.base import (
    Base,
    LongText,
    Money,
    OrgOwnedMixin,
    Str64,
    Str128,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Payment(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Money received against an invoice (P1 flow, P0 schema)."""

    __tablename__ = "payments"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "payment_number",
            name="uq_payments_organization_id_payment_number",
        ),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.Index("ix_payments_invoice_id_status", "invoice_id", "status"),
    )

    payment_number: Mapped[Str64] = mapped_column(nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Money] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    method: Mapped[PaymentMethod] = mapped_column(
        enum_col(PaymentMethod), nullable=False, default=PaymentMethod.BANK_TRANSFER
    )
    status: Mapped[PaymentStatus] = mapped_column(
        enum_col(PaymentStatus), nullable=False, default=PaymentStatus.SETTLED
    )
    reference: Mapped[Str128 | None] = mapped_column(nullable=True)
    notes: Mapped[LongText | None] = mapped_column(nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
