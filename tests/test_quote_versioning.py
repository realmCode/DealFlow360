"""Quote version immutability and the revision lifecycle."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.enums import QuoteVersionStatus
from tests.conftest import build_canonical_quote, money as parse

#: Everything except DRAFT must refuse in-place line edits.
IMMUTABLE_STATUSES = (
    QuoteVersionStatus.PENDING_APPROVAL,
    QuoteVersionStatus.APPROVED,
    QuoteVersionStatus.SENT,
    QuoteVersionStatus.NEGOTIATING,
    QuoteVersionStatus.CONFIRMED,
    QuoteVersionStatus.REJECTED,
    QuoteVersionStatus.SUPERSEDED,
)


async def _force_status(version_id: str, status: QuoteVersionStatus) -> None:
    """Set a version's status directly.

    Reaching every immutable state through the real workflow would make this
    file a workflow test. The statuses are reached legitimately elsewhere
    (approval, send, confirm, reject); here we only assert the guard.
    """
    import uuid

    from sqlalchemy import update

    from app.models.quote_version import QuoteVersion
    from tests.conftest import db_session

    async with db_session() as s:
        await s.execute(
            update(QuoteVersion)
            .where(QuoteVersion.id == uuid.UUID(version_id))
            .values(status=status)
        )
        await s.commit()


async def test_draft_version_accepts_line_edits(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    version = built["version"]
    assert version["status"] == "DRAFT"
    assert version["is_editable"] is True

    line = version["lines"][0]
    await sales.patch(
        f"/quote-versions/{built['version_id']}/lines/{line['id']}",
        json={"quantity": "50"},
        expect=200,
    )
    await sales.post(
        f"/quote-versions/{built['version_id']}/lines",
        json={
            "product_id": seeded["products"]["HW-MONITOR-27"],
            "quantity": "5",
            "discount_pct": "0",
        },
        expect=201,
    )
    await sales.delete(
        f"/quote-versions/{built['version_id']}/lines/{line['id']}", expect=204
    )


@pytest.mark.parametrize("status", IMMUTABLE_STATUSES, ids=lambda s: s.value)
async def test_non_draft_versions_reject_line_patch(seeded, status) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    line = built["version"]["lines"][0]
    await _force_status(built["version_id"], status)

    response = await sales.patch(
        f"/quote-versions/{built['version_id']}/lines/{line['id']}",
        json={"discount_pct": "1"},
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "IMMUTABLE_VERSION"
    assert body["details"]["status"] == status.value
    assert body["details"]["editable_statuses"] == ["DRAFT"]


@pytest.mark.parametrize("status", IMMUTABLE_STATUSES, ids=lambda s: s.value)
async def test_non_draft_versions_reject_line_delete(seeded, status) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    line = built["version"]["lines"][0]
    await _force_status(built["version_id"], status)

    response = await sales.delete(
        f"/quote-versions/{built['version_id']}/lines/{line['id']}"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IMMUTABLE_VERSION"


@pytest.mark.parametrize("status", IMMUTABLE_STATUSES, ids=lambda s: s.value)
async def test_non_draft_versions_reject_line_add(seeded, status) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _force_status(built["version_id"], status)

    response = await sales.post(
        f"/quote-versions/{built['version_id']}/lines",
        json={
            "product_id": seeded["products"]["HW-MONITOR-27"],
            "quantity": "1",
            "discount_pct": "0",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IMMUTABLE_VERSION"


@pytest.mark.parametrize(
    "status",
    [
        QuoteVersionStatus.CONFIRMED,
        QuoteVersionStatus.REJECTED,
        QuoteVersionStatus.SUPERSEDED,
    ],
    ids=lambda s: s.value,
)
async def test_terminal_versions_cannot_even_be_revised(seeded, status) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _force_status(built["version_id"], status)

    response = await sales.post(
        f"/quote-versions/{built['version_id']}/revisions",
        json={"reason": "trying anyway"},
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "VERSION_TERMINAL"
    assert body["details"]["status"] == status.value


@pytest.mark.parametrize(
    "status",
    [
        QuoteVersionStatus.PENDING_APPROVAL,
        QuoteVersionStatus.APPROVED,
        QuoteVersionStatus.SENT,
        QuoteVersionStatus.NEGOTIATING,
    ],
    ids=lambda s: s.value,
)
async def test_revisable_statuses_can_create_the_next_version(seeded, status) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _force_status(built["version_id"], status)

    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={"reason": f"revising from {status.value}"},
            expect=201,
        )
    ).json()
    assert new_version["version_number"] == 2
    assert new_version["parent_version_id"] == built["version_id"]
    assert new_version["revision_reason"] == f"revising from {status.value}"


async def test_revision_supersedes_the_parent_and_advances_the_quote(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]

    await sales.post(
        f"/quote-versions/{built['version_id']}/revisions",
        json={"reason": "customer asked for more"},
        expect=201,
    )

    parent = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert parent["status"] == "SUPERSEDED"

    quote = (await sales.get(f"/quotes/{built['quote']['id']}", expect=200)).json()
    assert quote["current_version_number"] == 2
    assert len(quote["versions"]) == 2


async def test_revision_copies_lines_and_applies_updates(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )

    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "deeper laptop discount",
                "line_updates": {laptop["id"]: {"discount_pct": "25"}},
            },
            expect=201,
        )
    ).json()

    assert len(new_version["lines"]) == 4, "all lines must be carried forward"
    new_laptop = next(
        line for line in new_version["lines"] if "Laptop" in line["description"]
    )
    assert parse(new_laptop["discount_pct"]) == Decimal("25.0000")
    assert parse(new_laptop["net_amount"]) == Decimal("90000.00")
    # Untouched lines keep their terms exactly.
    monitor = next(
        line for line in new_version["lines"] if "Monitor" in line["description"]
    )
    assert parse(monitor["discount_pct"]) == Decimal("16.0000")


async def test_revision_can_add_and_remove_lines(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    support = next(
        line for line in built["version"]["lines"] if "Support" in line["description"]
    )

    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "drop support, add monitors",
                "remove_line_ids": [support["id"]],
                "add_lines": [
                    {
                        "product_id": seeded["products"]["HW-MONITOR-27"],
                        "quantity": "10",
                        "discount_pct": "5",
                    }
                ],
            },
            expect=201,
        )
    ).json()

    descriptions = [line["description"] for line in new_version["lines"]]
    assert "Annual Support Plan" not in descriptions
    assert descriptions.count('27" Monitor') == 2
    assert parse(new_version["recurring_revenue"]) == Decimal("0.00")


async def test_revision_cannot_remove_every_line(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "0"),)
    )
    sales = seeded["sales"]
    line = built["version"]["lines"][0]
    response = await sales.post(
        f"/quote-versions/{built['version_id']}/revisions",
        json={"reason": "empty it", "remove_line_ids": [line["id"]]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_REVISION"


async def test_revision_recalculates_totals_from_scratch(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "zero the laptop discount",
                "line_updates": {laptop["id"]: {"discount_pct": "0"}},
            },
            expect=201,
        )
    ).json()
    # 132,710 + the 21,600 laptop discount that was removed.
    assert parse(new_version["net_revenue"]) == Decimal("154310.00")
    assert parse(new_version["total_discount"]) == Decimal("6490.00")


async def test_submit_requires_a_draft_version(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    response = await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_NOT_DRAFT"


async def test_submit_rejects_an_empty_quote(seeded) -> None:
    sales = seeded["sales"]
    deal = (
        await sales.post(
            "/deals",
            json={
                "name": "Empty deal",
                "customer_profile_id": seeded["customer_profile_id"],
            },
            expect=201,
        )
    ).json()
    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes", json={"title": "Empty"}, expect=201
        )
    ).json()
    response = await sales.post(
        f"/quote-versions/{quote['current_version_id']}/submit", json={}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_QUOTE"


async def test_version_numbers_are_sequential_and_unique(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]

    current = built["version_id"]
    for expected in (2, 3, 4):
        new_version = (
            await sales.post(
                f"/quote-versions/{current}/revisions",
                json={"reason": f"revision to v{expected}"},
                expect=201,
            )
        ).json()
        assert new_version["version_number"] == expected
        current = new_version["id"]

    quote = (await sales.get(f"/quotes/{built['quote']['id']}", expect=200)).json()
    numbers = [v["version_number"] for v in quote["versions"]]
    assert numbers == [1, 2, 3, 4]
    statuses = {v["version_number"]: v["status"] for v in quote["versions"]}
    assert statuses[1] == statuses[2] == statuses[3] == "SUPERSEDED"


async def test_auto_approved_quote_needs_no_human_when_within_policy(seeded) -> None:
    """A clean quote is approved on submit, and the audit trail says why."""
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "5", "5"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "APPROVED"
    assert version["requires_approval"] is False
    assert version["approved_at"] is not None

    events = (
        await sales.get(
            "/audit/events",
            params={"entity_id": built["version_id"], "event_type": "QUOTE_APPROVED"},
            expect=200,
        )
    ).json()
    assert events, "auto-approval must be audited"
    assert events[-1]["payload"]["auto_approved"] is True
    assert "no human approval is required" in events[-1]["payload"]["reason"]


async def test_send_requires_an_approved_version(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    response = await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_NOT_APPROVED"
