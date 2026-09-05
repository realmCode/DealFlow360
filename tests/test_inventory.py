"""Inventory: multi-warehouse allocation, backorders, concurrency safety."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.inventory import Inventory
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.inventory_service import InventoryService
from tests.conftest import (
    build_canonical_quote,
    db_session,
    money as parse,
)


async def _confirmed_order(
    seeded, lines=(("HW-LAPTOP-01", "100", "18"),)
) -> dict:
    """Drive a quote all the way to a confirmed order."""
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    customer = seeded["customer"]

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
    confirm = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()
    order = (
        await sales.get(f"/orders/{confirm['order']['id']}", expect=200)
    ).json()
    return {"built": built, "order": order}


async def _stock(sku: str) -> dict[str, Decimal]:
    async with db_session() as s:
        rows = (
            await s.execute(
                select(Warehouse.code, Inventory.quantity_on_hand, Inventory.quantity_reserved)
                .join(Inventory, Inventory.warehouse_id == Warehouse.id)
                .join(Product, Product.id == Inventory.product_id)
                .where(Product.sku == sku)
            )
        ).all()
    return {
        code: Decimal(on_hand) - Decimal(reserved) for code, on_hand, reserved in rows
    }


# ------------------------------------------------------------- allocation
async def test_sufficient_stock_ships_from_a_single_warehouse(seeded) -> None:
    """50 laptops fit in Main (60) — one shipment beats two."""
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "50", "18"),))
    ops = seeded["ops"]
    allocation = (
        await ops.post(
            f"/orders/{result['order']['id']}/allocate", json={}, expect=200
        )
    ).json()

    assert allocation["fully_allocated"] is True
    assert allocation["has_backorder"] is False
    assert allocation["shipment_count"] == 1
    line = allocation["lines"][0]
    assert parse(line["quantity_allocated"]) == Decimal("50")
    assert len(line["splits"]) == 1
    assert line["splits"][0]["warehouse_code"] == "MAIN"
    assert "single shipment" in line["explanation"]


async def test_the_canonical_sixty_forty_split_emerges_from_stock(seeded) -> None:
    """Main=60, East=40, order 100. No warehouse can cover it alone, so the
    algorithm takes the largest stock first and the 60/40 split falls out.
    Nothing about 60/40 is written down anywhere."""
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))
    ops = seeded["ops"]
    allocation = (
        await ops.post(
            f"/orders/{result['order']['id']}/allocate", json={}, expect=200
        )
    ).json()

    assert allocation["fully_allocated"] is True
    assert allocation["has_backorder"] is False
    assert allocation["shipment_count"] == 2

    line = allocation["lines"][0]
    split = {s["warehouse_code"]: Decimal(s["quantity"]) for s in line["splits"]}
    assert split == {"MAIN": Decimal("60"), "EAST": Decimal("40")}
    assert "no single warehouse held all 100 units" in line["explanation"]

    # Shipping cost reflects two shipments (120 + 180).
    assert parse(allocation["estimated_shipping_cost"]) == Decimal("300.00")

    # Availability is now zero everywhere; nothing was over-reserved.
    assert await _stock("HW-LAPTOP-01") == {"MAIN": Decimal("0"), "EAST": Decimal("0")}


async def test_split_changes_when_stock_changes(seeded) -> None:
    """Prove the algorithm is generic: move stock and the split moves."""
    admin = seeded["admin"]
    warehouses = {
        w["code"]: w["id"]
        for w in (await admin.get("/warehouses", expect=200)).json()
    }
    # Rebalance to 30 / 70.
    await admin.post(
        "/admin/inventory",
        json={
            "warehouse_id": warehouses["MAIN"],
            "product_id": seeded["products"]["HW-LAPTOP-01"],
            "quantity_on_hand": "30",
        },
        expect=201,
    )
    await admin.post(
        "/admin/inventory",
        json={
            "warehouse_id": warehouses["EAST"],
            "product_id": seeded["products"]["HW-LAPTOP-01"],
            "quantity_on_hand": "70",
        },
        expect=201,
    )

    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))
    ops = seeded["ops"]
    allocation = (
        await ops.post(
            f"/orders/{result['order']['id']}/allocate", json={}, expect=200
        )
    ).json()
    split = {
        s["warehouse_code"]: Decimal(s["quantity"])
        for s in allocation["lines"][0]["splits"]
    }
    assert split == {"EAST": Decimal("70"), "MAIN": Decimal("30")}


async def test_services_and_subscriptions_do_not_consume_stock(seeded) -> None:
    result = await _confirmed_order(
        seeded,
        lines=(
            ("HW-LAPTOP-01", "10", "18"),
            ("SV-INSTALL-01", "1", "0"),
            ("SB-SUPPORT-01", "1", "0"),
        ),
    )
    ops = seeded["ops"]
    allocation = (
        await ops.post(
            f"/orders/{result['order']['id']}/allocate", json={}, expect=200
        )
    ).json()
    assert allocation["fully_allocated"] is True
    # Only the laptop line needs a warehouse.
    assert len(allocation["lines"]) == 1
    assert allocation["shipment_count"] == 1

    order = (
        await seeded["sales"].get(f"/orders/{result['order']['id']}", expect=200)
    ).json()
    for line in order["lines"]:
        if not line["is_stock_tracked"]:
            assert parse(line["quantity_allocated"]) == parse(line["quantity"])


# -------------------------------------------------------------- shortage
async def test_shortage_creates_a_backorder_and_an_ops_alert(seeded) -> None:
    """Order 150 with only 100 in stock: 100 allocated, 50 backordered."""
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "150", "18"),))
    ops = seeded["ops"]
    allocation = (
        await ops.post(
            f"/orders/{result['order']['id']}/allocate", json={}, expect=200
        )
    ).json()

    assert allocation["fully_allocated"] is False
    assert allocation["has_backorder"] is True
    assert allocation["status"] == "PARTIALLY_ALLOCATED"
    line = allocation["lines"][0]
    assert parse(line["quantity_allocated"]) == Decimal("100")
    assert parse(line["quantity_backordered"]) == Decimal("50")
    assert "50 unit(s) backordered" in line["explanation"]

    order = (
        await ops.get(f"/orders/{result['order']['id']}", expect=200)
    ).json()
    backorders = [
        a for a in order["allocations"] if a["status"] == "BACKORDERED"
    ]
    assert len(backorders) == 1
    assert backorders[0]["warehouse_id"] is None
    assert parse(backorders[0]["quantity"]) == Decimal("50")

    items = (
        await ops.get(
            "/dashboard/attention-items",
            params={"type": "INVENTORY_SHORTAGE"},
            expect=200,
        )
    ).json()
    assert len(items) == 1
    assert items[0]["severity"] == "HIGH"
    assert items[0]["owner_role"] == "OPS"
    assert "50 x Business Laptop" in items[0]["reason"]
    assert items[0]["recommended_action"]


async def test_allow_partial_false_refuses_the_whole_allocation(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "150", "18"),))
    ops = seeded["ops"]
    response = await ops.post(
        f"/orders/{result['order']['id']}/allocate",
        json={"allow_partial": False},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

    # Nothing was reserved — the transaction rolled back entirely.
    assert await _stock("HW-LAPTOP-01") == {
        "MAIN": Decimal("60"),
        "EAST": Decimal("40"),
    }
    order = (await ops.get(f"/orders/{result['order']['id']}", expect=200)).json()
    assert order["allocations"] == []
    assert order["status"] == "CREATED"


async def test_restock_consolidates_the_backorder(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "150", "18"),))
    ops, admin = seeded["ops"], seeded["admin"]
    await ops.post(f"/orders/{result['order']['id']}/allocate", json={}, expect=200)

    warehouses = {
        w["code"]: w["id"]
        for w in (await admin.get("/warehouses", expect=200)).json()
    }
    await admin.post(
        "/admin/inventory/adjust",
        json={
            "warehouse_id": warehouses["MAIN"],
            "product_id": seeded["products"]["HW-LAPTOP-01"],
            "quantity_delta": "50",
            "reason": "Purchase order PO-1234 received",
        },
        expect=200,
    )

    order = (await ops.get(f"/orders/{result['order']['id']}", expect=200)).json()
    assert order["has_backorder"] is False
    assert order["fully_allocated"] is True
    assert order["status"] == "ALLOCATED"
    assert not [a for a in order["allocations"] if a["status"] == "BACKORDERED"]
    consolidated = [
        a for a in order["allocations"] if a["notes"] == "Consolidated after restock."
    ]
    assert consolidated
    assert parse(consolidated[0]["quantity"]) == Decimal("50")


# ------------------------------------------------------- no over-allocation
async def test_a_second_order_cannot_take_stock_already_reserved(seeded) -> None:
    first = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))
    ops = seeded["ops"]
    await ops.post(f"/orders/{first['order']['id']}/allocate", json={}, expect=200)

    second = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "10", "18"),))
    allocation = (
        await ops.post(
            f"/orders/{second['order']['id']}/allocate", json={}, expect=200
        )
    ).json()
    assert allocation["fully_allocated"] is False
    assert parse(allocation["lines"][0]["quantity_backordered"]) == Decimal("10")


async def test_database_refuses_over_reservation_even_if_code_is_wrong(
    seeded,
) -> None:
    """Belt and braces: the CHECK constraint is the last line of defence."""
    from sqlalchemy.exc import IntegrityError

    async with db_session() as s:
        row = (
            await s.execute(
                select(Inventory)
                .join(Product, Product.id == Inventory.product_id)
                .where(Product.sku == "HW-LAPTOP-01")
                .limit(1)
            )
        ).scalar_one()
        row.quantity_reserved = Decimal(row.quantity_on_hand) + Decimal("1")
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.concurrency
async def test_concurrent_allocations_cannot_over_allocate(seeded) -> None:
    """Two orders race for the same 100 laptops.

    ``SELECT ... FOR UPDATE`` must serialise them, so between them they
    reserve exactly 100 units and the loser is backordered — never 200
    reserved against 100 of stock.
    """
    first = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))
    second = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))

    async def allocate(order_id: str) -> dict:
        async with db_session() as s:
            order = await s.get(SalesOrder, uuid.UUID(order_id))
            actor = (
                await s.execute(
                    select(User).where(User.email == "ops@techsupply.com")
                )
            ).scalar_one()
            result = await InventoryService.allocate_order(
                s, order=order, actor=actor
            )
            await s.commit()
            return result

    results = await asyncio.gather(
        allocate(first["order"]["id"]),
        allocate(second["order"]["id"]),
        return_exceptions=True,
    )
    for result in results:
        assert not isinstance(result, Exception), result

    allocated = sum(
        Decimal(line["quantity_allocated"])
        for result in results
        for line in result["lines"]
    )
    backordered = sum(
        Decimal(line["quantity_backordered"])
        for result in results
        for line in result["lines"]
    )
    assert allocated == Decimal("100"), f"over/under-allocated: {allocated}"
    assert backordered == Decimal("100")
    assert await _stock("HW-LAPTOP-01") == {
        "MAIN": Decimal("0"),
        "EAST": Decimal("0"),
    }


# --------------------------------------------------------- manual override
async def test_manual_override_places_stock_where_ops_asks(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "20", "18"),))
    ops = seeded["ops"]
    order = result["order"]
    warehouses = {
        w["code"]: w["id"] for w in (await ops.get("/warehouses", expect=200)).json()
    }
    line_id = order["lines"][0]["id"]

    allocation = (
        await ops.post(
            f"/orders/{order['id']}/allocate",
            json={
                "overrides": [
                    {
                        "sales_order_line_id": line_id,
                        "warehouse_id": warehouses["EAST"],
                        "quantity": "20",
                    }
                ]
            },
            expect=200,
        )
    ).json()
    split = {
        s["warehouse_code"]: Decimal(s["quantity"])
        for s in allocation["lines"][0]["splits"]
    }
    # Automatic allocation would have chosen MAIN (higher priority, more stock).
    assert split == {"EAST": Decimal("20")}

    detail = (await ops.get(f"/orders/{order['id']}", expect=200)).json()
    assert detail["allocations"][0]["mode"] == "MANUAL_OVERRIDE"


async def test_manual_override_is_validated_against_real_availability(
    seeded,
) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "60", "18"),))
    ops = seeded["ops"]
    order = result["order"]
    warehouses = {
        w["code"]: w["id"] for w in (await ops.get("/warehouses", expect=200)).json()
    }
    response = await ops.post(
        f"/orders/{order['id']}/allocate",
        json={
            "overrides": [
                {
                    "sales_order_line_id": order["lines"][0]["id"],
                    "warehouse_id": warehouses["EAST"],  # only holds 40
                    "quantity": "60",
                }
            ]
        },
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "INSUFFICIENT_INVENTORY"
    assert body["details"]["available"] == "40.0000"


async def test_manual_override_cannot_exceed_the_ordered_quantity(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "10", "18"),))
    ops = seeded["ops"]
    order = result["order"]
    warehouses = {
        w["code"]: w["id"] for w in (await ops.get("/warehouses", expect=200)).json()
    }
    response = await ops.post(
        f"/orders/{order['id']}/allocate",
        json={
            "overrides": [
                {
                    "sales_order_line_id": order["lines"][0]["id"],
                    "warehouse_id": warehouses["MAIN"],
                    "quantity": "25",
                }
            ]
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OVERRIDE_EXCEEDS_LINE"


async def test_override_referencing_another_orders_line_is_rejected(seeded) -> None:
    first = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "10", "18"),))
    second = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "10", "18"),))
    ops = seeded["ops"]
    warehouses = {
        w["code"]: w["id"] for w in (await ops.get("/warehouses", expect=200)).json()
    }
    response = await ops.post(
        f"/orders/{first['order']['id']}/allocate",
        json={
            "overrides": [
                {
                    "sales_order_line_id": second["order"]["lines"][0]["id"],
                    "warehouse_id": warehouses["MAIN"],
                    "quantity": "5",
                }
            ]
        },
    )
    assert response.status_code == 404


# ----------------------------------------------------------------- fulfil
async def test_fulfillment_ships_one_shipment_per_warehouse(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))
    ops = seeded["ops"]
    await ops.post(f"/orders/{result['order']['id']}/allocate", json={}, expect=200)

    order = (
        await ops.post(
            f"/orders/{result['order']['id']}/fulfill",
            json={"carrier": "DHL", "tracking_number": "TRK-1"},
            expect=200,
        )
    ).json()

    assert len(order["fulfillments"]) == 2
    codes = {f["warehouse_name"] for f in order["fulfillments"]}
    assert codes == {"Main Warehouse", "East Depot"}
    assert order["status"] == "FULFILLED"
    assert order["fulfilled_at"] is not None
    assert all(f["status"] == "SHIPPED" for f in order["fulfillments"])
    assert sum(parse(f["shipping_cost"]) for f in order["fulfillments"]) == Decimal(
        "300.00"
    )

    # Shipping converts reservations into outbound movements.
    async with db_session() as s:
        rows = (
            await s.execute(
                select(Inventory.quantity_on_hand, Inventory.quantity_reserved)
                .join(Product, Product.id == Inventory.product_id)
                .where(Product.sku == "HW-LAPTOP-01")
            )
        ).all()
    for on_hand, reserved in rows:
        assert Decimal(on_hand) == Decimal("0")
        assert Decimal(reserved) == Decimal("0")


async def test_fulfilling_a_single_warehouse_leaves_the_order_partial(
    seeded,
) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "100", "18"),))
    ops = seeded["ops"]
    await ops.post(f"/orders/{result['order']['id']}/allocate", json={}, expect=200)
    warehouses = {
        w["code"]: w["id"] for w in (await ops.get("/warehouses", expect=200)).json()
    }

    order = (
        await ops.post(
            f"/orders/{result['order']['id']}/fulfill",
            json={"warehouse_id": warehouses["MAIN"]},
            expect=200,
        )
    ).json()
    assert order["status"] == "PARTIALLY_FULFILLED"
    assert len(order["fulfillments"]) == 1
    line = order["lines"][0]
    assert parse(line["quantity_fulfilled"]) == Decimal("60")


async def test_fulfilling_without_allocation_is_refused(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "10", "18"),))
    ops = seeded["ops"]
    response = await ops.post(f"/orders/{result['order']['id']}/fulfill", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTHING_TO_FULFILL"


# ------------------------------------------------------------- stock admin
async def test_stock_cannot_be_set_below_what_is_reserved(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "60", "18"),))
    ops, admin = seeded["ops"], seeded["admin"]
    await ops.post(f"/orders/{result['order']['id']}/allocate", json={}, expect=200)

    warehouses = {
        w["code"]: w["id"]
        for w in (await admin.get("/warehouses", expect=200)).json()
    }
    response = await admin.post(
        "/admin/inventory",
        json={
            "warehouse_id": warehouses["MAIN"],
            "product_id": seeded["products"]["HW-LAPTOP-01"],
            "quantity_on_hand": "10",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STOCK_BELOW_RESERVED"


async def test_negative_adjustment_cannot_take_stock_below_zero(seeded) -> None:
    admin = seeded["admin"]
    warehouses = {
        w["code"]: w["id"]
        for w in (await admin.get("/warehouses", expect=200)).json()
    }
    response = await admin.post(
        "/admin/inventory/adjust",
        json={
            "warehouse_id": warehouses["MAIN"],
            "product_id": seeded["products"]["HW-LAPTOP-01"],
            "quantity_delta": "-100",
            "reason": "shrinkage",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STOCK_NEGATIVE"


async def test_inventory_read_exposes_available_quantity(seeded) -> None:
    ops = seeded["ops"]
    rows = (
        await ops.get(
            "/inventory",
            params={"product_id": seeded["products"]["HW-LAPTOP-01"]},
            expect=200,
        )
    ).json()
    assert len(rows) == 2
    by_code = {r["warehouse_code"]: r for r in rows}
    assert parse(by_code["MAIN"]["quantity_on_hand"]) == Decimal("60")
    assert parse(by_code["MAIN"]["quantity_available"]) == Decimal("60")
    assert parse(by_code["EAST"]["quantity_available"]) == Decimal("40")
