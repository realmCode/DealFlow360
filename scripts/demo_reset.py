"""Put the demo tenant into a known, presentable state.

Run this immediately before a live demo. It talks to the running API over HTTP
using the seeded accounts — no database surgery, no fabricated rows. Everything
it creates goes through the same endpoints a user would hit.

    python -m scripts.demo_reset

What it does:

1. Restores the canonical stock levels (60 Main / 40 East laptops), because
   repeated demo runs legitimately consume inventory and an exhausted warehouse
   makes the allocator backorder everything. The split itself is still computed
   by the backend.
2. Creates one fresh DRAFT quotation carrying the canonical configuration, so
   the Quote Builder opens on numbers that match the script:

       net revenue 132,710.00 · margin 32,510.00 · margin 24.4970%
       blended risk 32.4440 (MEDIUM) · routes SALES_MANAGER then FINANCE

3. Prints the URL to open.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

API = "http://127.0.0.1:8010"
APP = "http://localhost:3000"
PASSWORD = "Password123!"

CANONICAL_LINES = (
    ("HW-LAPTOP-01", "100", "18"),
    ("HW-MONITOR-27", "100", "16"),
    ("SV-INSTALL-01", "1", "18"),
    ("SB-SUPPORT-01", "1", "0"),
)

STOCK = (
    ("MAIN", "HW-LAPTOP-01", "60"),
    ("EAST", "HW-LAPTOP-01", "40"),
    ("MAIN", "HW-MONITOR-27", "150"),
    ("EAST", "HW-MONITOR-27", "50"),
)


def call(method: str, path: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} failed with {exc.code}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach the API at {API}. Start it first:\n"
            f"    uvicorn app.main:app --port 8010\n({exc})"
        ) from exc


def login(email: str) -> str:
    return call("POST", "/auth/login", body={"email": email, "password": PASSWORD})["tokens"][
        "access_token"
    ]


def main() -> int:
    print("=" * 62)
    print("DEALFLOW360 DEMO RESET")
    print(f"api: {API}")
    print("=" * 62)

    admin = login("admin@techsupply.com")
    sales = login("sales@techsupply.com")

    # -- 1. stock ----------------------------------------------------------
    warehouses = {w["code"]: w["id"] for w in call("GET", "/warehouses", admin)}
    products = call("GET", "/products?limit=100", admin)
    catalogue = {p["sku"]: p for p in products.get("items", products)}

    print("\n[stock] restoring canonical levels")
    for code, sku, quantity in STOCK:
        call(
            "POST",
            "/admin/inventory",
            admin,
            {
                "warehouse_id": warehouses[code],
                "product_id": catalogue[sku]["id"],
                "quantity_on_hand": quantity,
                "reorder_point": "10",
            },
        )
        print(f"  {code:5} {sku:16} -> {quantity}")

    # -- 2. a fresh draft --------------------------------------------------
    customer = call("GET", "/customers", sales)[0]
    stamp = datetime.now().strftime("%H:%M")

    deal = call(
        "POST",
        "/deals",
        sales,
        {
            "name": f"Acme laptop refresh ({stamp})",
            "customer_profile_id": customer["id"],
            "stage": "PROPOSAL",
            "expected_value": "0",
        },
    )
    quote = call(
        "POST",
        f"/deals/{deal['id']}/quotes",
        sales,
        {
            "title": f"Acme laptop refresh ({stamp})",
            "order_discount_pct": "0",
            "lines": [
                {"product_id": catalogue[sku]["id"], "quantity": qty, "discount_pct": disc}
                for sku, qty, disc in CANONICAL_LINES
            ],
        },
    )
    version_id = quote["current_version_id"]
    totals = call("POST", f"/quote-versions/{version_id}/calculate", sales, {})
    policy = call("GET", f"/quote-versions/{version_id}/policy-results", sales)

    print(f"\n[quote] {quote['quote_number']} created as DRAFT for {customer['display_name']}")
    print(f"  net revenue   {totals['net_revenue']}")
    print(f"  margin        {totals['margin']}  ({totals['margin_pct']}%)")
    print(f"  blended risk  {policy['blended_risk']['score']}  ({policy['blended_risk']['band']})")
    print(f"  violations    {policy['violation_count']}")
    print(
        "  routes to     "
        + " then ".join(a["type"] for a in policy.get("required_approvals", []))
    )

    print("\n" + "=" * 62)
    print("OPEN THIS TO START THE DEMO")
    print(f"  {APP}/quotes/{quote['id']}/versions/{version_id}/build")
    print("=" * 62)
    print("\nSign in at", f"{APP}/login", "-> Demo accounts -> Sales")
    return 0


if __name__ == "__main__":
    sys.exit(main())
