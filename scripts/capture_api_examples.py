"""Drive the canonical flow and capture every response for the docs.

The API documentation is written from real payloads rather than from schemas,
because a schema says what a field *is* and an example says what it actually
looks like — including the string-encoded money, the enum spellings and the
shape of nested objects.

Writes `docs/api_examples.json`: a mapping of
``"METHOD /path"`` -> ``{status, request, response}``.

    python -m scripts.capture_api_examples

Runs against the live application in-process (no server needed) using the
configured DATABASE_URL, and seeds first so the flow has data.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db import dispose_engine, get_sessionmaker
from app.main import app

OUT = Path("docs/api_examples.json")
CAPTURED: dict[str, Any] = {}

#: Values that change every run. Replaced so a regenerated file diffs cleanly
#: and so the docs never embed a real signing artefact.
REDACT_KEYS = {"access_token", "refresh_token"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("<jwt>" if k in REDACT_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class Recorder:
    def __init__(self, client: AsyncClient, token: str | None = None) -> None:
        self._client = client
        self.token = token

    def as_(self, token: str | None) -> "Recorder":
        return Recorder(self._client, token)

    async def call(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        params: Any = None,
        headers: dict[str, str] | None = None,
        label: str | None = None,
        capture: bool = True,
    ) -> Any:
        merged = dict(headers or {})
        if self.token:
            merged["Authorization"] = f"Bearer {self.token}"
        response = await self._client.request(
            method, url, json=json_body, params=params, headers=merged
        )

        key = label or f"{method} {url}"
        if capture:
            try:
                body = response.json()
            except Exception:  # noqa: BLE001 - binary export responses
                body = f"<binary {len(response.content)} bytes>"
            entry: dict[str, Any] = {
                "status": response.status_code,
                "response": _redact(body),
            }
            if json_body is not None:
                entry["request"] = _redact(json_body)
            if params:
                entry["query"] = params
            if "content-type" in response.headers:
                entry["content_type"] = response.headers["content-type"]
            CAPTURED[key] = entry

        return response


async def main() -> int:
    if settings.is_testing:
        print("Refusing to run against the test database.", file=sys.stderr)
        return 1

    from scripts.seed import seed_canonical_data

    factory = get_sessionmaker()
    async with factory() as session:
        seed = await seed_canonical_data(session)
        await session.commit()
    print(f"seeded (idempotent={seed['idempotent']})")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://capture") as client:
        rec = Recorder(client)

        # ------------------------------------------------------- system
        await rec.call("GET", "/health")

        # --------------------------------------------------------- auth
        tokens: dict[str, str] = {}
        for role, email in (
            ("sales", "sales@techsupply.com"),
            ("manager", "manager@techsupply.com"),
            ("finance", "finance@techsupply.com"),
            ("ops", "ops@techsupply.com"),
            ("admin", "admin@techsupply.com"),
            ("customer", "customer@acme.com"),
        ):
            response = await rec.call(
                "POST",
                "/auth/login",
                json_body={"email": email, "password": settings.seed_default_password},
                capture=role == "sales",
            )
            tokens[role] = response.json()["tokens"]["access_token"]
            if role == "sales":
                refresh = response.json()["tokens"]["refresh_token"]

        sales = rec.as_(tokens["sales"])
        manager = rec.as_(tokens["manager"])
        finance = rec.as_(tokens["finance"])
        ops = rec.as_(tokens["ops"])
        admin = rec.as_(tokens["admin"])
        customer = rec.as_(tokens["customer"])

        await rec.call(
            "POST", "/auth/refresh", json_body={"refresh_token": refresh}
        )
        await sales.call("GET", "/users/me")

        # ---------------------------------------------------- error shapes
        await rec.call(
            "POST",
            "/auth/login",
            json_body={"email": "sales@techsupply.com", "password": "wrong"},
            label="POST /auth/login (401 wrong password)",
        )
        await rec.call(
            "POST",
            "/auth/login",
            json_body={"email": "not-an-email"},
            label="POST /auth/login (422 validation)",
        )
        await rec.call("GET", "/users/me", label="GET /users/me (401 no token)")
        await sales.call("GET", "/users", label="GET /users (403 admin only)")
        await sales.call(
            "GET", "/portal/quotes", label="GET /portal/quotes (403 internal user)"
        )
        await customer.call("GET", "/deals", label="GET /deals (403 portal user)")
        await sales.call(
            "GET",
            "/deals/00000000-0000-0000-0000-000000000000",
            label="GET /deals/{id} (404)",
        )

        # ---------------------------------------------------- admin config
        await admin.call("GET", "/admin/settings")
        await admin.call("GET", "/admin/sales-teams")
        await admin.call("GET", "/admin/product-variants")
        await admin.call("GET", "/admin/price-lists")

        # -------------------------------------------------------- catalog
        products_res = await sales.call("GET", "/products")
        products = {p["sku"]: p for p in products_res.json()["items"]}
        await sales.call("GET", f"/products/{products['HW-LAPTOP-01']['id']}")
        await sales.call(
            "GET", f"/products/{products['HW-LAPTOP-01']['id']}/variants"
        )
        await sales.call("GET", "/policies")
        await sales.call("GET", "/warehouses")
        await sales.call("GET", "/inventory")
        await sales.call("GET", "/customers")

        # ----------------------------------------------------- deal + quote
        deal = (
            await sales.call(
                "POST",
                "/deals",
                json_body={
                    "name": "Acme Q1 laptop refresh",
                    "customer_profile_id": seed["customer_profile_id"],
                    "stage": "PROPOSAL",
                },
            )
        ).json()
        await sales.call("GET", "/deals")
        await sales.call("GET", f"/deals/{deal['id']}", label="GET /deals/{deal_id}")

        quote = (
            await sales.call(
                "POST",
                f"/deals/{deal['id']}/quotes",
                json_body={
                    "title": "Acme Q1 laptop refresh",
                    "lines": [
                        {
                            "product_id": products["HW-LAPTOP-01"]["id"],
                            "quantity": "100",
                            "discount_pct": "18",
                        },
                        {
                            "product_id": products["HW-MONITOR-27"]["id"],
                            "quantity": "100",
                            "discount_pct": "16",
                        },
                        {
                            "product_id": products["SV-INSTALL-01"]["id"],
                            "quantity": "1",
                            "discount_pct": "18",
                        },
                        {
                            "product_id": products["SB-SUPPORT-01"]["id"],
                            "quantity": "1",
                            "discount_pct": "0",
                        },
                    ],
                },
                label="POST /deals/{deal_id}/quotes",
            )
        ).json()
        quote_id = quote["id"]
        version_id = quote["current_version_id"]

        await sales.call("GET", "/quotes")
        await sales.call("GET", f"/quotes/{quote_id}", label="GET /quotes/{quote_id}")
        await sales.call(
            "GET",
            f"/quote-versions/{version_id}",
            label="GET /quote-versions/{version_id}",
        )
        await sales.call(
            "POST",
            f"/quote-versions/{version_id}/calculate",
            label="POST /quote-versions/{version_id}/calculate",
        )
        await sales.call(
            "GET",
            f"/quote-versions/{version_id}/policy-results",
            label="GET /quote-versions/{version_id}/policy-results",
        )
        await sales.call(
            "GET",
            f"/quotes/{quote_id}/recommendations",
            label="GET /quotes/{quote_id}/recommendations",
        )

        # ------------------------------------------------------ simulation
        first_line = quote and (
            await sales.call(
                "GET", f"/quote-versions/{version_id}", capture=False
            )
        ).json()["lines"][0]["id"]
        await sales.call(
            "POST",
            f"/quote-versions/{version_id}/simulate",
            json_body={"line_discounts": {first_line: "25"}},
            label="POST /quote-versions/{version_id}/simulate",
        )

        # ---------------------------------------------------------- submit
        await sales.call(
            "POST",
            f"/quote-versions/{version_id}/submit",
            json_body={},
            label="POST /quote-versions/{version_id}/submit",
        )
        await sales.call(
            "GET",
            f"/quote-versions/{version_id}/impact",
            label="GET /quote-versions/{version_id}/impact",
        )
        await sales.call(
            "GET",
            f"/quote-versions/{version_id}/approval",
            label="GET /quote-versions/{version_id}/approval",
        )
        await sales.call(
            "PATCH",
            f"/quote-versions/{version_id}/lines/{first_line}",
            json_body={"discount_pct": "5"},
            label="PATCH /quote-versions/{v}/lines/{line_id} (409 immutable)",
        )

        # -------------------------------------------------------- approvals
        inbox = (await manager.call("GET", "/approvals/inbox")).json()
        request_id = inbox[0]["approval_request_id"]
        await manager.call(
            "GET",
            f"/approvals/{request_id}",
            label="GET /approvals/{request_id}",
        )
        await finance.call(
            "POST",
            f"/approvals/{request_id}/approve",
            json_body={"reason": "Jumping the queue."},
            label="POST /approvals/{id}/approve (403 wrong step)",
        )
        await manager.call(
            "POST",
            f"/approvals/{request_id}/approve",
            json_body={"reason": "200-unit volume justifies the extra points."},
            label="POST /approvals/{request_id}/approve",
        )
        await finance.call(
            "POST",
            f"/approvals/{request_id}/approve",
            json_body={"reason": "24.5% margin clears the 10% floor."},
            capture=False,
        )
        await sales.call(
            "POST",
            f"/quote-versions/{version_id}/send",
            json_body={},
            label="POST /quote-versions/{version_id}/send",
        )

        # ----------------------------------------------------------- portal
        await customer.call("GET", "/portal/quotes")
        portal = (
            await customer.call(
                "GET",
                f"/portal/quotes/{quote_id}",
                label="GET /portal/quotes/{quote_id}",
            )
        ).json()
        await customer.call(
            "GET",
            f"/portal/quotes/{quote_id}/messages",
            label="GET /portal/quotes/{quote_id}/messages",
        )
        laptop_line = next(
            line
            for line in portal["current_version"]["lines"]
            if "Laptop" in line["description"]
        )
        await customer.call(
            "POST",
            f"/portal/quotes/{quote_id}/messages",
            json_body={
                "message_type": "COUNTER_OFFER",
                "body": "We need 25% on the laptops to sign this quarter.",
                "lines": [
                    {
                        "quote_line_id": laptop_line["id"],
                        "requested_discount_pct": "25",
                    }
                ],
            },
            label="POST /portal/quotes/{quote_id}/messages (counter-offer)",
        )

        v2 = (await sales.call("GET", f"/quotes/{quote_id}", capture=False)).json()
        v2_id = v2["current_version_id"]
        await sales.call(
            "GET",
            f"/quote-versions/{v2_id}/impact",
            label="GET /quote-versions/{v}/impact (material change + stale)",
        )
        await customer.call(
            "POST",
            f"/portal/quotes/{quote_id}/confirm",
            json_body={},
            label="POST /portal/quotes/{id}/confirm (409 stale approval)",
        )
        await sales.call(
            "GET", f"/quotes/{quote_id}/negotiation", label="GET /quotes/{id}/negotiation"
        )

        # ------------------------------------------------------ re-approval
        for approver in (manager, finance):
            box = (await approver.call("GET", "/approvals/inbox", capture=False)).json()
            entry = next(i for i in box if str(i["quote_version_id"]) == str(v2_id))
            await approver.call(
                "POST",
                f"/approvals/{entry['approval_request_id']}/approve",
                json_body={"reason": "Re-approved the countered terms."},
                capture=False,
            )

        key = str(uuid.uuid4())
        confirm = (
            await customer.call(
                "POST",
                f"/portal/quotes/{quote_id}/confirm",
                json_body={"acceptance_note": "Approved by our procurement board."},
                headers={"Idempotency-Key": key},
                label="POST /portal/quotes/{quote_id}/confirm",
            )
        ).json()
        order_id = confirm["order"]["id"]
        await customer.call(
            "POST",
            f"/portal/quotes/{quote_id}/confirm",
            json_body={"acceptance_note": "Approved by our procurement board."},
            headers={"Idempotency-Key": key},
            label="POST /portal/quotes/{id}/confirm (idempotent replay)",
        )

        # ----------------------------------------------------------- orders
        await sales.call("GET", "/orders")
        await sales.call("GET", f"/orders/{order_id}", label="GET /orders/{order_id}")
        await ops.call(
            "POST",
            f"/orders/{order_id}/allocate",
            json_body={},
            label="POST /orders/{order_id}/allocate",
        )
        await ops.call(
            "GET",
            f"/orders/{order_id}/allocations",
            label="GET /orders/{order_id}/allocations",
        )
        await sales.call(
            "PATCH",
            f"/orders/{order_id}/promise",
            json_body={"promised_delivery_date": "2026-12-31"},
            label="PATCH /orders/{order_id}/promise",
        )
        fulfilled = (
            await ops.call(
                "POST",
                f"/orders/{order_id}/fulfill",
                json_body={"carrier": "DHL", "tracking_number": "TRK-ACME-001"},
                label="POST /orders/{order_id}/fulfill",
            )
        ).json()
        shipment_id = fulfilled["fulfillments"][0]["id"]
        await ops.call(
            "POST",
            f"/orders/{order_id}/fulfillments/{shipment_id}/deliver",
            json_body={"note": "Signed for at reception."},
            label="POST /orders/{id}/fulfillments/{fid}/deliver",
        )

        # ---------------------------------------------------------- billing
        schedules = (
            await finance.call(
                "GET", "/billing/schedules", params={"sales_order_id": order_id}
            )
        ).json()
        await finance.call(
            "GET",
            f"/billing/orders/{order_id}/summary",
            label="GET /billing/orders/{order_id}/summary",
        )
        await finance.call(
            "GET",
            "/billing/proration-preview",
            params={
                "full_period_amount": "1200",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "billed_from": "2026-07-01",
            },
        )
        recurring = next(s for s in schedules if s["billing_type"] == "RECURRING")
        invoice = (
            await finance.call(
                "POST",
                "/billing/invoices",
                json_body={"billing_schedule_id": recurring["id"]},
            )
        ).json()
        await finance.call("GET", "/billing/invoices")
        await finance.call(
            "POST",
            f"/billing/invoices/{invoice['id']}/payments",
            json_body={"amount": invoice["total_amount"], "method": "BANK_TRANSFER"},
            label="POST /billing/invoices/{invoice_id}/payments",
        )

        # ------------------------------------------ subscription lifecycle
        one_time = next(s for s in schedules if s["billing_type"] == "ONE_TIME")
        await finance.call(
            "POST",
            f"/billing/subscriptions/{one_time['id']}/change",
            json_body={"new_quantity": "2"},
            label="POST /billing/subscriptions/{id}/change (400 not recurring)",
        )
        cancelled = (
            await finance.call(
                "POST",
                f"/billing/subscriptions/{recurring['id']}/cancel",
                json_body={
                    "effective_date": recurring["period_start"],
                    "reason": "Customer consolidated onto another contract.",
                },
                label="POST /billing/subscriptions/{schedule_id}/cancel",
            )
        ).json()
        await finance.call("GET", "/billing/credit-notes")
        if cancelled.get("credit_note_id"):
            await finance.call(
                "GET",
                f"/billing/credit-notes/{cancelled['credit_note_id']}",
                label="GET /billing/credit-notes/{credit_note_id}",
            )

        # -------------------------------------------------------- dashboard
        await sales.call("GET", "/dashboard/control-tower")
        await sales.call("GET", "/dashboard/attention-items")
        await sales.call("GET", "/dashboard/deal-health")
        await sales.call(
            "GET",
            f"/dashboard/deal-health/{deal['id']}",
            label="GET /dashboard/deal-health/{deal_id}",
        )
        await sales.call("GET", "/audit/events", params={"limit": 5})
        await sales.call(
            "GET",
            f"/audit/quotes/{quote_id}/timeline",
            label="GET /audit/quotes/{quote_id}/timeline",
        )

        # ---------------------------------------------------------- reports
        for name in (
            "sales-performance",
            "approval-status",
            "products",
            "discounts",
            "pipeline",
            "discount-anomalies",
        ):
            await sales.call("GET", f"/reports/{name}")
        await sales.call("GET", "/reports/export/formats")
        await sales.call(
            "GET",
            "/reports/sales-performance/export",
            params={"format": "xlsx"},
            label="GET /reports/{report}/export (binary)",
        )

    await dispose_engine()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(CAPTURED, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(f"captured {len(CAPTURED)} responses -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
