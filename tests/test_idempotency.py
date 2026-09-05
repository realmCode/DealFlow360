"""Idempotency: retries must never duplicate a business entity."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.idempotency_key import IdempotencyKey
from app.models.inventory_allocation import InventoryAllocation
from app.models.sales_order import SalesOrder
from tests.conftest import build_canonical_quote, db_session, money as parse


async def _sent_quote(seeded, lines=(("HW-LAPTOP-01", "100", "18"),)) -> dict:
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    built = await build_canonical_quote(seeded, lines=lines)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            if str(item["quote_version_id"]) == str(built["version_id"]):
                await approver.post(
                    f"/approvals/{item['approval_request_id']}/approve",
                    json={"reason": "ok"},
                    expect=200,
                )
    await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}, expect=200
    )
    return built


async def _count(model) -> int:
    async with db_session() as s:
        return int(
            (await s.execute(select(func.count()).select_from(model))).scalar_one()
        )


# ------------------------------------------------------------ confirmation
async def test_duplicate_confirmation_with_the_same_key_returns_one_order(
    seeded,
) -> None:
    built = await _sent_quote(seeded)
    customer = seeded["customer"]
    key = str(uuid.uuid4())

    first = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm",
            json={"acceptance_note": "Approved by our board."},
            headers={"Idempotency-Key": key},
            expect=200,
        )
    ).json()
    second = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm",
            json={"acceptance_note": "Approved by our board."},
            headers={"Idempotency-Key": key},
            expect=200,
        )
    ).json()

    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert first["order"]["id"] == second["order"]["id"]
    assert first["order"]["order_number"] == second["order"]["order_number"]
    assert await _count(SalesOrder) == 1


async def test_duplicate_confirmation_without_a_key_still_returns_one_order(
    seeded,
) -> None:
    """The DB unique constraint on quote_version_id is the real guarantee."""
    built = await _sent_quote(seeded)
    customer = seeded["customer"]

    first = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()
    second = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()

    assert first["order"]["id"] == second["order"]["id"]
    assert second["idempotent_replay"] is True
    assert "already confirmed" in second["message"]
    assert await _count(SalesOrder) == 1


@pytest.mark.concurrency
async def test_concurrent_confirmations_create_exactly_one_order(seeded) -> None:
    """Five simultaneous confirms. Exactly one order, no 500s."""
    from app.models.customer_profile import CustomerProfile
    from app.models.quote import Quote
    from app.models.quote_version import QuoteVersion
    from app.models.user import User
    from app.services.order_service import OrderService

    built = await _sent_quote(seeded)
    quote_id = uuid.UUID(built["quote"]["id"])
    version_id = uuid.UUID(built["version_id"])

    async def confirm() -> str | Exception:
        try:
            async with db_session() as s:
                quote = await s.get(Quote, quote_id)
                version = await s.get(QuoteVersion, version_id)
                profile = (
                    await s.execute(select(CustomerProfile).limit(1))
                ).scalar_one()
                actor = (
                    await s.execute(
                        select(User).where(User.email == "customer@acme.com")
                    )
                ).scalar_one()
                order, existed = await OrderService.confirm_quote_version(
                    s,
                    quote=quote,
                    version=version,
                    profile=profile,
                    actor=actor,
                )
                await s.commit()
                return str(order.id)
        except Exception as exc:  # captured and asserted on below
            return exc

    results = await asyncio.gather(*[confirm() for _ in range(5)])
    order_ids = {r for r in results if isinstance(r, str)}
    errors = [r for r in results if isinstance(r, Exception)]

    assert await _count(SalesOrder) == 1, "a race produced duplicate orders"
    assert len(order_ids) <= 1
    # Any loser must fail cleanly, not with an unhandled integrity error.
    for error in errors:
        from app.errors import ConflictError

        assert isinstance(error, ConflictError), type(error)


async def test_reusing_a_key_with_a_different_body_is_a_conflict(seeded) -> None:
    built = await _sent_quote(seeded)
    customer = seeded["customer"]
    key = str(uuid.uuid4())

    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm",
        json={"acceptance_note": "first"},
        headers={"Idempotency-Key": key},
        expect=200,
    )
    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm",
        json={"acceptance_note": "second, different"},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_idempotency_key_is_persisted_with_its_response(seeded) -> None:
    built = await _sent_quote(seeded)
    customer = seeded["customer"]
    key = "client-generated-key-001"

    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm",
        json={},
        headers={"Idempotency-Key": key},
        expect=200,
    )

    async with db_session() as s:
        record = (
            await s.execute(
                select(IdempotencyKey).where(IdempotencyKey.key == key)
            )
        ).scalar_one()

    assert record.status.value == "COMPLETED"
    assert record.endpoint.endswith("/confirm")
    assert record.method == "POST"
    assert record.request_hash
    assert record.response_status_code == 200
    assert record.entity_type == "sales_order"
    assert record.entity_id is not None
    assert record.completed_at is not None
    assert record.expires_at is not None
    assert record.response_body["order"]["order_number"].startswith("SO-")


# -------------------------------------------------------------- allocation
async def test_duplicate_allocation_with_the_same_key_is_replayed(seeded) -> None:
    built = await _sent_quote(seeded)
    customer, ops = seeded["customer"], seeded["ops"]
    confirm = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()
    order_id = confirm["order"]["id"]
    key = str(uuid.uuid4())

    first = (
        await ops.post(
            f"/orders/{order_id}/allocate",
            json={},
            headers={"Idempotency-Key": key},
            expect=200,
        )
    ).json()
    second = (
        await ops.post(
            f"/orders/{order_id}/allocate",
            json={},
            headers={"Idempotency-Key": key},
            expect=200,
        )
    ).json()

    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert first["shipment_count"] == second["shipment_count"] == 2
    # Two allocation rows total, not four — and no double reservation.
    assert await _count(InventoryAllocation) == 2

    inventory = (
        await ops.get(
            "/inventory",
            params={"product_id": seeded["products"]["HW-LAPTOP-01"]},
            expect=200,
        )
    ).json()
    for row in inventory:
        assert parse(row["quantity_available"]) == Decimal("0")
        assert parse(row["quantity_reserved"]) == parse(row["quantity_on_hand"])


async def test_allocation_without_a_key_is_naturally_safe(seeded) -> None:
    """Re-allocating with nothing outstanding must be a no-op, not a re-reserve."""
    built = await _sent_quote(seeded)
    customer, ops = seeded["customer"], seeded["ops"]
    confirm = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()
    order_id = confirm["order"]["id"]

    await ops.post(f"/orders/{order_id}/allocate", json={}, expect=200)
    second = (
        await ops.post(f"/orders/{order_id}/allocate", json={}, expect=200)
    ).json()

    assert second["lines"] == []  # nothing left to allocate
    assert await _count(InventoryAllocation) == 2
    inventory = (
        await ops.get(
            "/inventory",
            params={"product_id": seeded["products"]["HW-LAPTOP-01"]},
            expect=200,
        )
    ).json()
    assert sum(parse(r["quantity_reserved"]) for r in inventory) == Decimal("100")


async def test_keys_are_scoped_per_endpoint(seeded) -> None:
    """The same key on two endpoints is two independent operations."""
    built = await _sent_quote(seeded)
    customer, ops = seeded["customer"], seeded["ops"]
    key = "shared-key"

    confirm = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm",
            json={},
            headers={"Idempotency-Key": key},
            expect=200,
        )
    ).json()
    allocation = (
        await ops.post(
            f"/orders/{confirm['order']['id']}/allocate",
            json={},
            headers={"Idempotency-Key": key},
            expect=200,
        )
    ).json()
    assert allocation["idempotent_replay"] is False

    async with db_session() as s:
        count = (
            await s.execute(
                select(func.count())
                .select_from(IdempotencyKey)
                .where(IdempotencyKey.key == key)
            )
        ).scalar_one()
    assert int(count) == 2


async def test_a_failed_operation_does_not_lock_the_key_forever(seeded) -> None:
    """A rejected attempt must leave the key usable for a genuine retry."""
    built = await build_canonical_quote(seeded)
    sales, customer = seeded["sales"], seeded["customer"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    # Not sent yet -> not confirmable, and the key transaction rolls back.
    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm",
        json={},
        headers={"Idempotency-Key": "retry-key"},
    )
    assert response.status_code == 404  # not visible to the portal yet

    async with db_session() as s:
        count = (
            await s.execute(
                select(func.count())
                .select_from(IdempotencyKey)
                .where(IdempotencyKey.key == "retry-key")
            )
        ).scalar_one()
    # The whole request rolled back, so no key row was committed.
    assert int(count) == 0
