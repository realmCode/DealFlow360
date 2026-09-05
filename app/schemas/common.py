"""Shared schema base classes and primitives.

``Decimal`` fields serialise to JSON **strings** (Pydantic v2 default), which
keeps money lossless across the wire — a JSON number would be parsed as an
IEEE-754 double by any JavaScript client and quietly lose cents.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

MoneyField = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
PercentField = Annotated[Decimal, Field(ge=0, le=100, max_digits=9, decimal_places=4)]
QuantityField = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]


class ApiModel(BaseModel):
    """Request/response base."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="forbid",
    )


class ReadModel(ApiModel):
    """Response base — tolerant of extra ORM attributes."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class TimestampedRead(ReadModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Page(ReadModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class MessageResponse(ReadModel):
    message: str
    detail: dict[str, Any] | None = None


class ErrorBody(ReadModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ReadModel):
    """The envelope returned by every non-2xx response."""

    error: ErrorBody
