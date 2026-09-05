# BACKEND API DOCUMENTATION

**Base URL:** `http://127.0.0.1:8000` (no path prefix — `API_PREFIX` is empty)
**Spec:** [`openapi.json`](./openapi.json) — 103 paths, 117 operations, 187 schemas
**Interactive:** `/docs` (Swagger UI) · `/redoc` · `/openapi.json`

Every example in this document was **captured from a live run** of the
canonical flow, not written by hand. The raw capture is
[`api_examples.json`](./api_examples.json) (82 recorded request/response
pairs), regenerated with:

```bash
python -m scripts.capture_api_examples
```

Labels used below:

| Label | Meaning |
|---|---|
| **VERIFIED** | Response body reproduced from a live capture |
| 🔍 **INFERRED FROM CODE** | Shape read from the source; not exercised in the capture |
| ❌ **NOT IMPLEMENTED** | No code path exists |

---

## 1. Conventions that apply to every endpoint

### 1.1 Money is a JSON string

```json
{ "net_revenue": "132710.00", "margin_pct": "24.4970" }
```

Never a number. A JSON number is parsed as an IEEE-754 double by every
JavaScript client and silently loses cents. Parse with a decimal library
(`decimal.js`, `big.js`) — **not** `parseFloat`.

Precision by field class: amounts 2dp, unit prices 4dp, percentages 4dp,
quantities 4dp, proration factors 8dp.

### 1.2 One error envelope, always

Every non-2xx response — including framework validation errors and 404s for
unknown routes — has this shape:

```json
{
  "error": {
    "code": "STALE_APPROVAL",
    "message": "Human-readable sentence, safe to display.",
    "details": { }
  }
}
```

`code` is the stable contract. Branch on it, never on `message`. `details` is
always present (possibly `{}`) and carries machine-usable context — see §3.

There is **no** `{"detail": ...}` response and **no** bare FastAPI validation
array anywhere; both are rewritten by exception handlers in
[`app/main.py`](../app/main.py).

### 1.3 Authentication

`Authorization: Bearer <access_token>` on everything except
`/`, `/health`, `/docs`, `/redoc`, `/openapi.json`, `/auth/signup`,
`/auth/login`, `/auth/refresh`.

### 1.4 Pagination

Every list endpoint returns:

```json
{ "items": [ ], "total": 4, "limit": 25, "offset": 0 }
```

`total` is the **unpaginated** count, so it drives the pager directly.

Shared query parameters:

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | `25` | 1–200. Outside that → 422 |
| `offset` | int | `0` | ≥ 0 |
| `sort_by` | string | per endpoint | Allowlisted; unknown value → 422 `INVALID_SORT_FIELD` with the allowed list in `details` |
| `sort_dir` | `asc`\|`desc` | `desc` | |

Reference collections returned whole (not paginated): `/policies`,
`/warehouses`, `/inventory`, `/customers`, `/billing/schedules`,
`/billing/invoices`, `/billing/credit-notes`, `/approvals/inbox`,
`/portal/quotes`, `/admin/sales-teams`, `/admin/product-variants`,
`/admin/price-lists`.

### 1.5 Period filter

Used by every report and accepted on some lists.

| Parameter | Values |
|---|---|
| `period` | `today` `week` `month` `quarter` `year` `all` `custom` (default `all`) |
| `date_from`, `date_to` | ISO dates. **Both required** when `period=custom`; both bounds inclusive |

`period=custom` without both → 422 `PERIOD_RANGE_REQUIRED`.
`date_to < date_from` → 422 `INVALID_PERIOD_RANGE`.

### 1.6 Idempotency

Send `Idempotency-Key: <uuid>` on `POST /portal/quotes/{id}/confirm` and
`POST /orders/{id}/allocate`. Same key + same body replays the stored response
with `idempotent_replay: true`. Same key + **different** body → 409
`IDEMPOTENCY_KEY_REUSED`. Concurrent identical request → 409
`IDEMPOTENT_REQUEST_IN_FLIGHT`.

### 1.7 Response format families

Not every endpoint shares an envelope. There are five distinct families:

| Family | Used by | Shape |
|---|---|---|
| Bare object | detail reads, mutations | The resource |
| `Page[T]` | paginated lists | `{items, total, limit, offset}` |
| Bare array | reference collections, inbox | `[...]` |
| Error | all non-2xx | `{error: {code, message, details}}` |
| **Binary** | `/reports/{name}/export` | File bytes + `Content-Disposition` |
| `204` | `DELETE` line, dismiss recommendation | Empty body |

---

## 2. System

### GET `/health` — liveness and dependency check

Auth: none. **VERIFIED**

```json
{
  "status": "ok",
  "app": "DealFlow360",
  "version": "1.0.0",
  "environment": "development",
  "database": "up",
  "event_handlers": { "*": 1 }
}
```

`status` is `"degraded"` and `database` becomes `"down: <ExceptionName>"` when
the database check fails. Always HTTP 200 — inspect `status`.

### GET `/` — service descriptor

Auth: none. Excluded from the OpenAPI schema. **VERIFIED**

```json
{"name":"DealFlow360","version":"1.0.0","docs":"/docs","openapi":"/openapi.json","health":"/health"}
```

---

## 3. Authentication

### POST `/auth/login`

Auth: none. Rate limited (see §3.4).

**Request**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `email` | string (email) | yes | Valid address |
| `password` | string | yes | 1–72 bytes |

```json
{ "email": "sales@techsupply.com", "password": "Password123!" }
```

**200** — **VERIFIED**

```json
{
  "tokens": {
    "access_token": "<jwt>",
    "refresh_token": "<jwt>",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "user": {
    "id": "10b3c1ca-211e-4bd6-93ea-0c76b384b3c1",
    "email": "sales@techsupply.com",
    "full_name": "Sam Rivera",
    "role": "SALES",
    "organization_id": "cf77ceba-30d2-4c24-b480-e19e9a8e44ca",
    "organization_name": "TechSupply Solutions",
    "organization_kind": "SELLER",
    "is_internal": true
  }
}
```

`expires_in` is seconds (3600 = `ACCESS_TOKEN_EXPIRE_MINUTES` 60).
Refresh token lifetime is 7 days and is **not** reported in the payload.

**401 wrong password** — **VERIFIED**

```json
{"error":{"code":"AUTHENTICATION_FAILED","message":"Invalid email or password.","details":{}}}
```

The same message is returned for an unknown email, so the endpoint does not
disclose whether an account exists.

**422 validation** — **VERIFIED**. Note the framework errors are wrapped:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request payload failed validation.",
    "details": {
      "errors": [
        {
          "type": "value_error",
          "loc": ["body", "email"],
          "msg": "value is not a valid email address: An email address must have an @-sign.",
          "input": "not-an-email",
          "ctx": {"reason": "An email address must have an @-sign."}
        },
        {
          "type": "missing",
          "loc": ["body", "password"],
          "msg": "Field required",
          "input": {"email": "not-an-email"}
        }
      ]
    }
  }
}
```

`details.errors[].loc` maps directly to a form field: drop the leading
`"body"` and the remainder is the field path.

**Other 401 codes:** `USER_DISABLED`, `ORGANIZATION_DISABLED`.

### POST `/auth/signup`

Auth: none. **201** returns the same `LoginResponse` as login.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `email` | string (email) | yes | Globally unique |
| `password` | string | yes | 8–72 bytes; must mix letters and at least one non-letter |
| `full_name` | string | yes | 1–255 |
| `role` | `RoleCode` | no | Default `SALES` |
| `organization_id` | uuid | conditional | Join an existing org |
| `organization_name` | string | conditional | Or create one (max 255) |
| `organization_kind` | `OrganizationKind` | no | Default `SELLER` |

Exactly one of `organization_id` / `organization_name` is required →
otherwise 400 `ORGANIZATION_REQUIRED`.

**Errors:** 409 `EMAIL_ALREADY_REGISTERED`; 400 `ROLE_ORG_MISMATCH` (a
`CUSTOMER` role in a `SELLER` org, or an internal role in a `CUSTOMER` org);
404 `NOT_FOUND` for an unknown `organization_id`.

### POST `/auth/refresh`

**Request:** `{"refresh_token": "<jwt>"}`

**200** — **VERIFIED**. Returns a `TokenPair` only (no `user`):

```json
{"access_token":"<jwt>","refresh_token":"<jwt>","token_type":"bearer","expires_in":3600}
```

**401 `WRONG_TOKEN_TYPE`** — **VERIFIED**. Tokens are typed:

```json
{"error":{"code":"WRONG_TOKEN_TYPE","message":"Expected a refresh token, got 'access'.","details":{}}}
```

Refresh tokens are **stateless** — there is no revocation list, so a leaked
one stays valid until expiry. Deactivating the user does immediately break
refresh, because the user row is re-read.

### 3.4 Rate limiting

`/auth/login`, `/auth/signup` and `/auth/refresh` are limited per IP **and**
per email — 10 attempts per 15 minutes by default.

**429** 🔍 **INFERRED FROM CODE** (asserted by `tests/test_security_hardening.py`):

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many attempts. Try again in 812 seconds.",
    "details": {"retry_after_seconds": 812, "limit": 10, "window_seconds": 900}
  }
}
```

Also sends a `Retry-After` header in seconds. A successful authentication
clears that identity's history.

### 3.5 Token contents

Access token claims: `sub` (user id), `type`, `org`, `role`, `email`, `iat`,
`exp`, `jti`. Refresh token: `sub`, `type`, `iat`, `exp`, `jti`.

**Do not trust the embedded `role`** for authorization decisions beyond UI
hints — it is observability only. The server re-reads the user row on every
request, so a role change or deactivation takes effect immediately rather than
at expiry.

### 3.6 Not implemented

| Feature | Status |
|---|---|
| Magic-link portal login | ❌ **NOT IMPLEMENTED**. The PDF permits "magic link, **or** email and password"; password auth satisfies it |
| Logout endpoint | ❌ **NOT IMPLEMENTED**. Tokens are stateless — discard them client-side |
| Password reset | ❌ **NOT IMPLEMENTED** |
| Email verification | ❌ **NOT IMPLEMENTED** |
| Refresh-token revocation | ❌ **NOT IMPLEMENTED** |
| 2FA | ❌ **NOT IMPLEMENTED** |

---

## 4. Users

### GET `/users/me`

Auth: any authenticated user. **200** — **VERIFIED**

```json
{
  "id": "10b3c1ca-211e-4bd6-93ea-0c76b384b3c1",
  "created_at": "2026-09-05T19:35:59.733941Z",
  "updated_at": "2026-09-05T20:13:24.441349Z",
  "email": "sales@techsupply.com",
  "full_name": "Sam Rivera",
  "role": "SALES",
  "organization_id": "cf77ceba-30d2-4c24-b480-e19e9a8e44ca",
  "organization_name": "TechSupply Solutions",
  "is_active": true,
  "is_internal": true,
  "last_login_at": "2026-09-05T20:13:24.435880Z"
}
```

Call this on boot to resolve the role and choose the shell (internal workspace
vs customer portal).

**401 no token** — **VERIFIED**

```json
{"error":{"code":"AUTHENTICATION_FAILED","message":"Missing bearer token.","details":{}}}
```

### GET `/users` · POST `/users`

Auth: `ADMIN`. `GET` returns a bare array of `UserRead`. `POST` → 201.

**403 for any other role** — **VERIFIED**:

```json
{"error":{"code":"FORBIDDEN","message":"Role SALES cannot perform this action.","details":{"your_role":"SALES","allowed_roles":["ADMIN"]}}}
```

`details.allowed_roles` lets the UI render an accurate permission screen.

---

## 5. Admin configuration (all `ADMIN`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/products` | Create a catalog product |
| PATCH | `/admin/products/{product_id}` | Update; includes `is_promoted` |
| POST · GET · PATCH | `/admin/product-variants[/{id}]` | Variants (attribute, deltas) |
| POST · GET · PATCH | `/admin/price-lists[/{id}]` | Tier price lists |
| POST | `/admin/warehouses` | Create a warehouse |
| GET · PATCH | `/admin/warehouses/{warehouse_id}` | Read / edit priority and shipping cost |
| POST | `/admin/inventory` | Set stock for a warehouse/product pair |
| POST | `/admin/inventory/adjust` | Stock movement; a positive delta also consolidates backorders |
| POST · PATCH | `/admin/policies[/{policy_id}]` | Governance policies |
| GET · PATCH | `/admin/settings` | Per-tenant thresholds and risk weights |
| POST · GET · PATCH | `/admin/sales-teams[/{id}]` | Sales teams |
| POST · DELETE | `/admin/sales-teams/{id}/members[/{user_id}]` | Team membership |
| POST | `/admin/seed` | Load the demo dataset (idempotent) |

### GET `/admin/settings` — **VERIFIED**

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "organization_id": "cf77ceba-30d2-4c24-b480-e19e9a8e44ca",
  "finance_escalation_threshold": "60.0000",
  "risk_discount_overage_weight": "3.0000",
  "risk_breadth_weight": "5.0000",
  "risk_margin_weight": "5.0000",
  "risk_depth_weight": "0.4000",
  "stalled_deal_days": 14,
  "discount_anomaly_sigma": "2.0000",
  "discount_anomaly_min_samples": 5,
  "approval_sla_hours": 24,
  "recommendation_min_margin_pct": "0.0000"
}
```

Created from environment defaults on first read, so a tenant that has never
opened the screen behaves exactly as before. `PATCH` accepts any subset.

**Changing `finance_escalation_threshold` changes approval routing
immediately** — it does not change the score, only who must sign.

### POST `/admin/products`

| Field | Type | Required | Constraints |
|---|---|---|---|
| `sku` | string | yes | 1–64, unique per org |
| `name` | string | yes | 1–255 |
| `description` | string | no | |
| `category` | `ProductCategory` | yes | |
| `list_price` | decimal | yes | ≥ 0, 4dp |
| `internal_cost` | decimal | yes | ≥ 0, 4dp |
| `tax_rate_pct` | decimal | no | 0–100, default 0 |
| `uom` | string | no | Default `"EACH"` |
| `billing_type` | `BillingType` | no | Default `ONE_TIME` |
| `recurring_interval` | `RecurringInterval` | conditional | Required iff `RECURRING`; forbidden otherwise |
| `default_recurring_periods` | int | no | 1–120, default 1 |
| `is_stock_tracked` | bool | no | Default false |

**409 `SKU_EXISTS`** on a duplicate. Warehouse and policy creation return
`WAREHOUSE_CODE_EXISTS` / `POLICY_CODE_EXISTS` equivalently.

### POST `/admin/seed` — **VERIFIED**

```json
{
  "status": "ok",
  "seller_organization_id": "…",
  "customer_organization_id": "…",
  "customer_profile_id": "…",
  "created": {"roles":0,"organizations":0,"users":0,"customer_profiles":0,
              "contacts":0,"products":0,"warehouses":0,"inventory":0,
              "policies":0,"sales_teams":0},
  "idempotent": true,
  "demo_password": "Password123!",
  "users": ["sales@techsupply.com", "…"],
  "products": {"HW-LAPTOP-01": "…"},
  "warehouses": {"MAIN": "…", "EAST": "…"}
}
```

`idempotent: true` means nothing was created — safe to call repeatedly.

---

## 6. Catalog, policies, inventory (read; all internal roles)

### GET `/products` — paginated

Filters: `category`, `include_inactive`, `is_promoted`, `is_stock_tracked`,
`q` (SKU or name). Sortable: `name` `sku` `category` `list_price` `created_at`.
Always ordered by category first so a grouped picker stays stable.

**200** — **VERIFIED** (one item shown)

```json
{
  "items": [
    {
      "id": "c2572808-1f40-4e8d-8d6a-a1f530c41090",
      "created_at": "2026-09-05T19:36:01.759189Z",
      "updated_at": "2026-09-05T19:36:01.759194Z",
      "sku": "HW-MONITOR-27",
      "name": "27\" Monitor",
      "description": "27-inch QHD IPS monitor with USB-C docking.",
      "category": "HARDWARE",
      "list_price": "400.0000",
      "internal_cost": "200.0000",
      "tax_rate_pct": "0.0000",
      "uom": "EACH",
      "billing_type": "ONE_TIME",
      "recurring_interval": null,
      "default_recurring_periods": 1,
      "is_stock_tracked": true,
      "is_active": true,
      "is_promoted": false,
      "unit_margin": "200.0000"
    }
  ],
  "total": 4, "limit": 25, "offset": 0
}
```

`internal_cost` and `unit_margin` are employee-only. They are **absent from
every portal schema** — see §11.

### GET `/products/{product_id}/variants`

Bare array of `ProductVariantRead`. A variant's `price_delta` / `cost_delta`
are applied on top of the parent product when attached to a quote line.

### GET `/policies` — bare array

Filters: `policy_type`, `include_inactive`. **VERIFIED** (one of seven):

```json
{
  "id": "46b27a8e-f513-4ab3-b573-5a076337cb2e",
  "created_at": "…", "updated_at": "…",
  "code": "GOLD-HW-CEILING",
  "name": "Gold tier hardware discount ceiling",
  "description": "Gold customers may receive up to 15% off hardware without escalation. Anything above requires Sales Manager sign-off.",
  "policy_type": "CATEGORY_DISCOUNT_CEILING",
  "customer_tier": "GOLD",
  "product_category": "HARDWARE",
  "customer_profile_id": null,
  "threshold_value": "15.0000",
  "comparison": "LTE",
  "unit": "PERCENT",
  "required_action": "SALES_MANAGER",
  "severity": "MEDIUM",
  "priority": 10,
  "is_active": true,
  "effective_from": null,
  "effective_to": null,
  "config": {}
}
```

### GET `/warehouses` — bare array — **VERIFIED**

```json
[
  {"id":"03c7c56d-…","code":"MAIN","name":"Main Warehouse","region":"West",
   "city":"San Jose","country":"US","priority":10,
   "shipping_cost_per_shipment":"120.00","is_active":true,
   "created_at":"…","updated_at":"…"},
  {"id":"4d4d542e-…","code":"EAST","name":"East Depot","region":"East",
   "city":"Newark","country":"US","priority":20,
   "shipping_cost_per_shipment":"180.00","is_active":true,
   "created_at":"…","updated_at":"…"}
]
```

`priority` (lower wins) and `shipping_cost_per_shipment` drive the allocation
split.

### GET `/inventory` — bare array

Filters: `product_id`, `warehouse_id`. **VERIFIED** (one row)

```json
{
  "id": "0ca63d7d-…", "created_at": "…", "updated_at": "…",
  "warehouse_id": "03c7c56d-…", "warehouse_code": "MAIN",
  "warehouse_name": "Main Warehouse",
  "product_id": "c2572808-…", "product_sku": "HW-MONITOR-27",
  "product_name": "27\" Monitor",
  "quantity_on_hand": "150.0000",
  "quantity_reserved": "0.0000",
  "quantity_available": "150.0000",
  "quantity_inbound": "0.0000",
  "reorder_point": "10.0000",
  "expected_restock_at": null
}
```

`quantity_available = on_hand − reserved`, enforced by a database CHECK.

---

## 7. Customers

| Method | Path | Auth |
|---|---|---|
| GET | `/customers` | internal |
| POST | `/customers` | `SALES` `MANAGER` `ADMIN` |
| GET | `/customers/{customer_id}` | internal |
| PATCH | `/customers/{customer_id}` | `SALES` `MANAGER` `ADMIN` |
| GET | `/customers/{customer_id}/contacts` | internal |
| POST | `/customers/{customer_id}/contacts` | `SALES` `MANAGER` `ADMIN` |

**GET `/customers`** — bare array — **VERIFIED**

```json
[{
  "id":"6c57cfc8-676e-4ace-9baa-05a9cb6fc9df",
  "created_at":"…","updated_at":"…",
  "customer_organization_id":"a360528f-6e37-4f79-896a-20808229f49c",
  "customer_organization_name":"Acme Corporation",
  "display_name":"Acme Corporation",
  "tier":"GOLD","payment_terms":"NET_30","currency":"USD",
  "credit_limit":"500000.00","credit_used":"0.00",
  "credit_available":"500000.00","tax_rate_pct":"0.0000",
  "is_active":true
}]
```

**POST `/customers`** creates the buyer organization on the fly when only
`customer_organization_name` is supplied. Supply one of
`customer_organization_id` / `customer_organization_name`, else 400
`CUSTOMER_ORGANIZATION_REQUIRED`. Other errors: 400
`ORGANIZATION_NOT_CUSTOMER`, 409 `CUSTOMER_PROFILE_EXISTS` (with the existing
`customer_profile_id` in `details`).

---

## 8. Deals

### GET `/deals` — paginated

Filters: `stage` (drives the Kanban column), `owner_user_id`,
`customer_profile_id`, `q` (reference or name). Sortable: `created_at`
`updated_at` `reference` `name` `stage` `expected_value`
`expected_close_date`.

**200** — **VERIFIED** (one item)

```json
{
  "items": [{
    "id": "…", "created_at": "…", "updated_at": "…",
    "reference": "D-00001",
    "name": "Acme Q1 laptop refresh",
    "customer_profile_id": "6c57cfc8-…",
    "customer_display_name": "Acme Corporation",
    "customer_tier": "GOLD",
    "owner_user_id": "10b3c1ca-…",
    "primary_contact_id": null,
    "stage": "PROPOSAL",
    "currency": "USD",
    "expected_value": "0.00",
    "expected_close_date": null,
    "notes": null,
    "quotes": [
      {"id":"…","quote_number":"Q-00001","title":"Acme Q1 laptop refresh",
       "status":"OPEN","current_version_number":1}
    ]
  }],
  "total": 1, "limit": 25, "offset": 0
}
```

### POST `/deals` — 201

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1–255 |
| `customer_profile_id` | uuid | yes | 404 if outside your org |
| `reference` | string | no | Auto-generated `D-00001` if omitted |
| `stage` | `DealStage` | no | Default `QUALIFICATION` |
| `expected_value` | decimal | no | ≥ 0, default 0 |
| `expected_close_date` | date | no | |
| `primary_contact_id` | uuid | no | |
| `notes` | string | no | |

Currency is inherited from the customer profile and is not settable.

### PATCH `/deals/{deal_id}`

Accepts `name`, `stage`, `expected_value`, `expected_close_date`, `notes`.

⚠️ **NOT VERIFIED** — stage transitions are unguarded, so a `CLOSED_WON` deal
can be moved back to `QUALIFICATION`. Tracked as P1-9 in
[`BACKEND_GAP_ANALYSIS.md`](./BACKEND_GAP_ANALYSIS.md).

---

## 9. Quotes

### GET `/quotes` — paginated (the Quotations list and Kanban)

Filters: `status`, `version_status`, `deal_stage`, `owner_user_id`,
`customer_profile_id`, `risk_band`, `is_stale`, `requires_approval`, `q`.

**200** — **VERIFIED** (one item)

```json
{
  "items": [{
    "quote_id": "…", "quote_number": "Q-00001",
    "title": "Acme Q1 laptop refresh", "status": "OPEN",
    "deal_id": "…", "deal_reference": "D-00001", "deal_stage": "PROPOSAL",
    "customer_profile_id": "…", "customer_display_name": "Acme Corporation",
    "customer_tier": "GOLD",
    "current_version_id": "…", "current_version_number": 1,
    "current_version_status": "DRAFT",
    "total_revenue": "132710.00", "net_revenue": "132710.00",
    "margin_pct": "24.4970", "effective_discount_pct": "17.4689",
    "blended_risk_score": "32.4440", "risk_band": "MEDIUM",
    "requires_approval": true, "is_stale": false,
    "owner_user_id": "…", "owner_name": "Sam Rivera",
    "line_count": 4, "version_count": 1,
    "age_days": 0,
    "last_activity_at": "…", "created_at": "…"
  }],
  "total": 1, "limit": 25, "offset": 0
}
```

Everything a B2 card needs — customer, amount, stage — in one request.

### GET `/quotes/{quote_id}` — **VERIFIED**

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "quote_number": "Q-00001",
  "title": "Acme Q1 laptop refresh",
  "deal_id": "…",
  "status": "OPEN",
  "current_version_number": 1,
  "current_version_id": "…",
  "versions": [
    {"id":"…","version_number":1,"status":"DRAFT","source":"INITIAL",
     "total_revenue":"132710.00","margin_pct":"24.4970",
     "blended_risk_score":"32.4440","is_stale":false,"created_at":"…"}
  ]
}
```

### POST `/deals/{deal_id}/quotes` — 201

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | 1–255 |
| `payment_terms` | `PaymentTerms` | no | Defaults to the customer's terms |
| `valid_until` | date | no | |
| `order_discount_pct` | decimal | no | 0–100, default 0 |
| `lines[]` | `QuoteLineCreate[]` | no | Creates v1 with lines in one call |

`QuoteLineCreate`:

| Field | Type | Required | Constraints |
|---|---|---|---|
| `product_id` | uuid | yes | Must be active and in your org |
| `product_variant_id` | uuid | no | Must belong to that product |
| `quantity` | decimal | yes | > 0, 4dp |
| `discount_pct` | decimal | no | 0–100, default 0 |
| `unit_list_price` | decimal | no | ≥ 0. Overrides catalog and price list |
| `description` | string | no | ≤ 255. Defaults to the product name |
| `recurring_periods` | int | no | 1–120. Only for recurring products |
| `notes` | string | no | |

**`unit_cost` cannot be supplied.** Every request model sets
`extra="forbid"`, so an unexpected field is a 422 rather than being ignored.
Cost is copied server-side from the catalog.

**Price precedence:** explicit `unit_list_price` → matching tier price list →
`product.list_price`. A variant's `price_delta`/`cost_delta` is then added.

### GET `/quote-versions/{version_id}` — **VERIFIED** (abridged)

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "quote_id": "…", "version_number": 1,
  "parent_version_id": null,
  "status": "DRAFT", "source": "INITIAL",
  "revision_reason": null, "created_by_user_id": "…",
  "currency": "USD", "payment_terms": "NET_30", "valid_until": null,

  "order_discount_pct": "0.0000", "order_discount_amount": "0.00",
  "gross_revenue": "160800.00", "total_discount": "28090.00",
  "net_revenue": "132710.00", "tax_amount": "0.00",
  "total_revenue": "132710.00", "total_cost": "100200.00",
  "margin": "32510.00", "margin_pct": "24.4970",
  "effective_discount_pct": "17.4689",
  "one_time_revenue": "132410.00", "recurring_revenue": "300.00",

  "blended_risk_score": "32.4440", "risk_band": "MEDIUM",
  "requires_approval": true, "is_stale": false, "stale_reason": null,

  "calculated_at": "…", "submitted_at": null, "approved_at": null,
  "sent_at": null, "confirmed_at": null, "rejected_at": null,
  "superseded_at": null,
  "is_editable": true,

  "lines": [{
    "id": "…", "created_at": "…", "updated_at": "…",
    "quote_version_id": "…", "product_id": "…", "product_variant_id": null,
    "line_number": 1, "description": "Business Laptop", "category": "HARDWARE",
    "quantity": "100.0000",
    "unit_list_price": "1200.0000", "unit_cost": "800.0000",
    "unit_net_price": "984.0000",
    "discount_pct": "18.0000", "discount_amount": "21600.00",
    "order_discount_amount": "0.00", "effective_discount_pct": "18.0000",
    "gross_amount": "120000.00", "net_amount": "98400.00",
    "tax_rate_pct": "0.0000", "tax_amount": "0.00",
    "total_amount": "98400.00",
    "line_cost": "80000.00", "line_margin": "18400.00",
    "line_margin_pct": "18.6992",
    "billing_type": "ONE_TIME", "recurring_interval": null,
    "recurring_periods": 1, "is_stock_tracked": true, "notes": null
  }]
}
```

`is_editable` is the single flag the UI should gate line editing on — true
only for `DRAFT`.

### Line mutation (all `SALES` `MANAGER` `ADMIN`, `DRAFT` only)

| Method | Path | Success |
|---|---|---|
| POST | `/quote-versions/{version_id}/lines` | 201 → full `QuoteVersionRead` |
| PATCH | `/quote-versions/{v}/lines/{line_id}` | 200 → full `QuoteVersionRead` |
| DELETE | `/quote-versions/{v}/lines/{line_id}` | **204, empty body** |

All three return the recalculated **whole version**, so the UI never has to
recompute a total.

`QuoteLineUpdate` accepts `quantity`, `discount_pct`, `unit_list_price`,
`description`, `recurring_periods`, `notes`. At least one is required → 422.

**409 `IMMUTABLE_VERSION`** — **VERIFIED**, with actionable `details`:

```json
{
  "error": {
    "code": "IMMUTABLE_VERSION",
    "message": "This version is awaiting approval. Create a revision (POST /quote-versions/{id}/revisions) to change it.",
    "details": {
      "quote_version_id": "…",
      "version_number": 1,
      "status": "PENDING_APPROVAL",
      "editable_statuses": ["DRAFT"]
    }
  }
}
```

The message varies by status — see [`ENTITY_STATE_LIFECYCLES.md`](./ENTITY_STATE_LIFECYCLES.md) §1.

### PATCH `/quote-versions/{version_id}/discount`

`{"order_discount_pct": "5"}` → 200 `QuoteVersionRead`. `DRAFT` only.

The order tier **compounds** with each line's own discount:
`effective = 100 × (1 − (1−line/100) × (1−order/100))`. That compounded figure
is what policy ceilings are evaluated against, so moving a giveaway from the
lines to the order cannot bypass a per-line ceiling.

### POST `/quote-versions/{version_id}/calculate`

Recalculates and snapshots. Returns `QuoteVersionRead`. Any internal role.
Call after adding an upsell line so the margin indicator updates immediately.

### GET `/quote-versions/{version_id}/policy-results` — **VERIFIED** (abridged)

```json
{
  "quote_version_id": "…",
  "evaluated_at": "…",
  "policy_results": [{
    "id": "…", "quote_version_id": "…", "policy_id": "…", "quote_line_id": "…",
    "rule": "CATEGORY_DISCOUNT_CEILING",
    "status": "VIOLATED",
    "subject": "Business Laptop",
    "actual_value": "18.0000", "threshold_value": "15.0000",
    "overage_points": "3.0000", "unit": "PERCENT",
    "scope_category": "HARDWARE", "scope_tier": "GOLD",
    "reason": "Hardware discount of 18% on 'Business Laptop' exceeds the Gold tier ceiling of 15% by 3 percentage points.",
    "required_action": "SALES_MANAGER",
    "severity": "MEDIUM",
    "risk_contribution": "11.6735",
    "detail": {
      "policy_code": "GOLD-HW-CEILING", "line_number": 1,
      "line_net_amount": "98400.00", "revenue_share": "74.1466",
      "weighted_overage": "2.2244",
      "line_discount_pct": "18.0000", "order_discount_pct": "0.0000",
      "effective_discount_pct": "18.0000"
    },
    "evaluated_at": "…"
  }],
  "blended_risk": {
    "score": "32.4440", "band": "MEDIUM",
    "tier": "GOLD", "tier_sensitivity": "1.10",
    "components": [
      {"name":"WEIGHTED_DISCOUNT_OVERAGE","raw_value":"2.5023","weight":"3.0",
       "points":"7.5069","cap":"45",
       "explanation":"Revenue-weighted ceiling overage of 2.5023 percentage points x weight 3 = 7.5069 points (cap 45)."},
      {"name":"VIOLATION_BREADTH","raw_value":"3","weight":"5.0","points":"15.0000","cap":"15","explanation":"…"},
      {"name":"MARGIN_SHORTFALL","raw_value":"0","weight":"5.0","points":"0.0000","cap":"40","explanation":"…"},
      {"name":"DISCOUNT_DEPTH","raw_value":"17.4689","weight":"0.4","points":"6.9876","cap":"15","explanation":"…"}
    ],
    "formula": "min(100, (min(45, S(overage_pts x revenue_share) x 3.0) + … ) x tier_sensitivity)",
    "explanation": "Blended risk 32.444/100 (MEDIUM) = (7.5069 overage + 15 breadth + 0 margin + 6.9876 depth) x 1.1 Gold tier sensitivity."
  },
  "required_approvals": [
    {"type":"SALES_MANAGER","reason":"…","triggered_by":["…"]},
    {"type":"FINANCE","reason":"…","triggered_by":["…"]}
  ],
  "requires_approval": true,
  "violation_count": 4
}
```

Every number arrives with its arithmetic. Render `components` as the score
breakdown rather than showing a bare figure.

### POST `/quote-versions/{version_id}/simulate` — what-if

`SALES`-visible to all internal roles. **Persists nothing.**

**Request** — at least one field required, else 422:

| Field | Type | Notes |
|---|---|---|
| `line_discounts` | `{uuid: decimal}` | New discount per existing line, 0–100 |
| `line_quantities` | `{uuid: decimal}` | New quantity per existing line, > 0 |
| `order_discount_pct` | decimal | 0–100 |
| `payment_terms` | `PaymentTerms` | |

**200** — 🔍 **INFERRED FROM CODE** (asserted by `tests/test_simulation.py`, which
verifies the prediction equals a real submit exactly):

```json
{
  "quote_version_id": "…",
  "simulated_at": "…",
  "baseline":  { "…": "same shape as proposed" },
  "proposed": {
    "gross_revenue": "…", "total_discount": "…",
    "order_discount_pct": "0.0000", "order_discount_amount": "0.00",
    "net_revenue": "…", "tax_amount": "…", "total_revenue": "…",
    "total_cost": "…", "margin": "…", "margin_pct": "…",
    "effective_discount_pct": "…",
    "blended_risk_score": "…", "risk_band": "HIGH",
    "risk_components": [], "risk_explanation": "…",
    "requires_approval": true,
    "required_approvals": ["SALES_MANAGER", "FINANCE"],
    "violation_count": 2, "violations": ["…"],
    "payment_terms": "NET_30",
    "lines": [{"quote_line_id":"…","description":"…","category":"HARDWARE",
               "quantity":"…","discount_pct":"…","effective_discount_pct":"…",
               "net_amount":"…","line_margin":"…","line_margin_pct":"…"}]
  },
  "margin_delta": "-8400.00",
  "margin_pct_delta": "-5.1019",
  "revenue_delta": "-8400.00",
  "risk_delta": "9.3899",
  "approvals_added": ["FINANCE"],
  "approvals_removed": [],
  "verdict": "Margin falls from 24.4970% to 19.3951%. Blended risk moves from 32.4440 (MEDIUM) to 41.8339 (HIGH). This would newly require FINANCE approval.",
  "persisted": false
}
```

`verdict` is a complete sentence, safe to display verbatim.

**404** if a line id is not on this version.

### POST `/quote-versions/{version_id}/submit`

`{"note": "optional, ≤2000"}` → **200** `DecisionFabricResult` (§10).

Transitions `DRAFT` → `PENDING_APPROVAL`, or straight to `APPROVED` when no
policy fires. Even an auto-approval writes an `approval_requests` row with
zero steps, so a later material change has a decision to invalidate.

**Errors:** 409 `VERSION_NOT_DRAFT`; 400 `EMPTY_QUOTE`.

### POST `/quote-versions/{version_id}/revisions` — 201

| Field | Type | Notes |
|---|---|---|
| `reason` | string | **Required**, 1–2000 |
| `line_updates` | `{uuid: QuoteLineUpdate}` | Keyed by existing line id |
| `add_lines` | `QuoteLineCreate[]` | |
| `remove_line_ids` | `uuid[]` | |
| `payment_terms` | `PaymentTerms` | |
| `order_discount_pct` | decimal | Carried forward if omitted |

Supersedes the parent, re-runs the Decision Fabric and submits, atomically.
Returns the **new** `QuoteVersionRead`.

**Errors:** 409 `VERSION_TERMINAL` (`CONFIRMED`/`REJECTED`/`SUPERSEDED`);
400 `EMPTY_REVISION`.

### POST `/quote-versions/{version_id}/send`

`{"note": "optional"}` → 200. `APPROVED` → `SENT`, creates the negotiation
thread. **409 `VERSION_NOT_APPROVED`** otherwise.

### GET `/quotes/{quote_id}/recommendations` — **VERIFIED**

```json
{
  "quote_id": "…",
  "quote_version_id": "…",
  "recommendations": [{
    "kind": "CROSS_SELL",
    "product_id": "…",
    "product_name": "Annual Support Plan",
    "suggested_quantity": "100",
    "estimated_revenue": "30000.00",
    "estimated_margin": "25000.00",
    "estimated_margin_pct": "83.3333",
    "reason": "The quote contains 200 hardware units but no subscription line. 'Annual Support Plan' is the standard attach for this configuration.",
    "impact": "Adding it would raise 30000.00 of revenue at 83.3333% margin (25000.00 gross profit).",
    "confidence": "HIGH",
    "is_promoted": true,
    "detail": {"category":"SUBSCRIPTION","sku":"SB-SUPPORT-01",
               "unit_list_price":"300.0000","is_promoted":true}
  }]
}
```

`is_promoted` drives the promotion tag. Promoted products sort first, then by
confidence. Returns `{"quote_id":…, "recommendations": []}` when the quote has
no version.

### POST `/quotes/{quote_id}/recommendations/{product_id}/dismiss`

**204, empty body.** Scoped to the current version — a revision offers
dismissed suggestions again, because the numbers have changed.

### POST `/quotes/{quote_id}/lose`

`{"reason": "required"}` → 200 `QuoteRead`. Sets `LOST` and closes the deal as
`CLOSED_LOST` when no sibling quote is still live.

**Errors:** 409 `QUOTE_ALREADY_LOST`, 409 `QUOTE_ALREADY_CONFIRMED`.

---

## 10. Decision Fabric

### GET `/quote-versions/{version_id}/impact`

A **pure read**, rebuilt from `decision_impacts` + `policy_results`. Calling
it repeatedly creates nothing.

**200** — **VERIFIED** (abridged; captured after the customer counter-offer)

```json
{
  "quote_id": "…", "quote_version_id": "…", "previous_version_id": "…",
  "evaluated_at": "…",
  "changes": [
    {"field":"discount_pct","subject":"Business Laptop","quote_line_id":"…",
     "old_value":"18.0000","new_value":"25.0000","material":true}
  ],
  "material_changes": [
    {"field":"discount_pct","subject":"Business Laptop","quote_line_id":"…",
     "old":"18.0000","new":"25.0000","severity":"HIGH",
     "reason":"Discount on 'Business Laptop' increased from 18% to 25% (+7 percentage points), which must be re-checked against the category ceiling."},
    {"field":"margin_pct","subject":"Quote margin","old":"24.4970","new":"19.3951","severity":"HIGH","reason":"…"}
  ],
  "policy_results": [],
  "stale_decisions": [
    {"approval_request_id":"…","previous_decision":"APPROVED",
     "reason":"Approval of version 1 is no longer valid: Discount on 'Business Laptop' increased from 18% to 25% …",
     "decided_at":"…","decided_by":"finance@techsupply.com"}
  ],
  "affected_entities": [{"type":"approval_request","id":"…","reason":"…"}],
  "required_approvals": [{"type":"SALES_MANAGER","reason":"…","triggered_by":[]}],
  "attention_items": [
    {"type":"STALE_APPROVAL","severity":"CRITICAL","title":"Approval invalidated on Q-00001 v2",
     "reason":"…","impact":"…","owner_role":"FINANCE","recommended_action":"…"}
  ],
  "explanation": {
    "summary": "…",
    "causal_chain": [
      "discount_pct on Business Laptop: 18.0000 -> 25.0000",
      "effective_discount_pct on Blended discount: 17.4689 -> 22.6928",
      "margin_pct on Quote margin: 24.4970 -> 19.3951",
      "Previous approval APPROVED -> STALE",
      "Approval pending with SALES_MANAGER, FINANCE"
    ],
    "what_changed": "…", "why_it_matters": "…",
    "who_is_affected": "…",
    "what_happens_next": "Customer confirmation is blocked until the new approval is granted."
  },
  "has_material_change": true,
  "blocks_confirmation": true
}
```

`has_material_change` and `blocks_confirmation` are the two flags to branch on.
`explanation.causal_chain` renders directly as an ordered list.

### GET `/quote-versions/{version_id}/approval` — **VERIFIED**

```json
{
  "quote_version_id": "…",
  "requires_approval": true,
  "approval_request": {
    "id": "…", "status": "PENDING",
    "reason": "…", "current_step_sequence": 1, "stale_reason": null,
    "steps": [
      {"sequence":1,"level":"SALES_MANAGER","required_role":"MANAGER","status":"PENDING"},
      {"sequence":2,"level":"FINANCE","required_role":"FINANCE","status":"PENDING"}
    ]
  }
}
```

`approval_request` is `null` when none exists.

---

## 11. Approvals

### GET `/approvals/inbox` — `MANAGER` `FINANCE` `ADMIN`

Bare array. Only steps awaiting **this caller's** role at the current
sequence. **VERIFIED**

```json
[{
  "approval_request_id": "…", "approval_step_id": "…",
  "quote_id": "…", "quote_version_id": "…",
  "quote_number": "Q-00001", "version_number": 1,
  "title": "Acme Q1 laptop refresh",
  "customer_name": "Acme Corporation",
  "level": "SALES_MANAGER", "sequence": 1,
  "reason": "Sales Manager approval required for 3 reasons: …",
  "blended_risk_score": "32.4440",
  "total_revenue": "132710.00",
  "margin_pct": "24.4970",
  "requested_by_email": "sales@techsupply.com",
  "is_reapproval": false,
  "waiting_since": "…"
}]
```

`is_reapproval: true` means this was approved before and the terms changed —
the most important flag on the screen.

**403 for `SALES`** — **VERIFIED**:
`{"code":"FORBIDDEN","details":{"your_role":"SALES","allowed_roles":["ADMIN","FINANCE","MANAGER"]}}`

### GET `/approvals/{request_id}` — any internal role — **VERIFIED** (abridged)

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "quote_id": "…", "quote_version_id": "…",
  "quote_number": "Q-00001", "version_number": 1,
  "customer_name": "Acme Corporation",
  "status": "PENDING",
  "requested_by_user_id": "…", "requested_by_email": "sales@techsupply.com",
  "reason": "…",
  "required_levels": [{"type":"SALES_MANAGER","reason":"…","triggered_by":[]}],
  "policy_summary": {"violation_count":4,"blended_risk":{},"required_approvals":[],"violations":[]},
  "blended_risk_score": "32.4440",
  "current_step_sequence": 1,
  "decided_at": null, "stale_at": null, "stale_reason": null,
  "steps": [{
    "id":"…","sequence":1,"level":"SALES_MANAGER","required_role":"MANAGER",
    "status":"PENDING","reason":"…","assigned_user_id":null,
    "decided_by_user_id":null,"decided_by_email":null,
    "decision_reason":null,"decided_at":null
  }],
  "decisions": [],
  "financials": {
    "version_number": 1,
    "gross_revenue":"160800.00","total_discount":"28090.00",
    "net_revenue":"132710.00","tax_amount":"0.00","total_revenue":"132710.00",
    "total_cost":"100200.00","margin":"32510.00","margin_pct":"24.4970",
    "effective_discount_pct":"17.4689","blended_risk_score":"32.4440",
    "risk_band":"MEDIUM"
  }
}
```

`financials` is the exact set of numbers under review — show these on the
approval screen so the decision is made against the real figures.

### POST `/approvals/{request_id}/{approve,reject,request-revision}`

`MANAGER` `FINANCE` `ADMIN`. Body: `{"reason": "required, 1–2000"}`.

**200** — **VERIFIED**

```json
{
  "approval_request": { },
  "quote_version_status": "PENDING_APPROVAL",
  "message": "Sales Manager approved. Now awaiting Finance approval."
}
```

`message` is written for display. `quote_version_status` tells you where the
version landed: `PENDING_APPROVAL` (more steps), `APPROVED`, `REJECTED`, or
`DRAFT` (revision requested).

**403 wrong step** — **VERIFIED**

```json
{
  "error": {
    "code": "WRONG_APPROVER_ROLE",
    "message": "Step 1 requires the MANAGER role; you hold FINANCE.",
    "details": {"required_role":"MANAGER","your_role":"FINANCE","level":"SALES_MANAGER"}
  }
}
```

**Other errors:**

| Code | HTTP | When |
|---|---|---|
| `SELF_APPROVAL_FORBIDDEN` | 403 | Actor authored or submitted the quote. `details` carries all three user ids |
| `APPROVAL_NOT_PENDING` | 409 | Request already decided. `details.status` |
| `NO_PENDING_STEP` | 409 | Step already decided. `details.already_decided[]` |
| `NOT_FOUND` | 404 | Unknown, or another organization's request |

---

## 12. Customer portal (`CUSTOMER` only)

Structural redaction: `unit_cost`, `line_cost`, `line_margin`,
`line_margin_pct`, `total_cost`, `margin`, `margin_pct`,
`blended_risk_score`, `risk_band`, `requires_approval` and `stale_reason` are
**absent from these schemas entirely**. A field that does not exist cannot be
leaked.

### GET `/portal/quotes` — bare array — **VERIFIED**

```json
[{
  "quote_id": "…", "quote_number": "Q-00001",
  "title": "Acme Q1 laptop refresh",
  "current_version_id": "…", "version_number": 1,
  "status": "SENT",
  "total_revenue": "132710.00", "currency": "USD",
  "valid_until": null,
  "awaiting_customer": true,
  "can_confirm": true,
  "blocked_reason": null
}]
```

### GET `/portal/quotes/{quote_id}` — **VERIFIED** (abridged)

```json
{
  "quote_id": "…", "quote_number": "Q-00001",
  "title": "Acme Q1 laptop refresh",
  "seller_name": "TechSupply Solutions",
  "status": "OPEN",
  "current_version": {
    "id": "…", "quote_id": "…", "version_number": 1,
    "status": "SENT", "currency": "USD", "payment_terms": "NET_30",
    "valid_until": null,
    "gross_revenue": "160800.00", "total_discount": "28090.00",
    "net_revenue": "132710.00", "tax_amount": "0.00",
    "total_revenue": "132710.00", "effective_discount_pct": "17.4689",
    "one_time_revenue": "132410.00", "recurring_revenue": "300.00",
    "sent_at": "…", "confirmed_at": null,
    "lines": [{
      "id": "…", "product_id": "…", "line_number": 1,
      "description": "Business Laptop", "category": "HARDWARE",
      "quantity": "100.0000",
      "unit_list_price": "1200.0000", "unit_net_price": "984.0000",
      "discount_pct": "18.0000", "discount_amount": "21600.00",
      "effective_discount_pct": "18.0000",
      "gross_amount": "120000.00", "net_amount": "98400.00",
      "tax_amount": "0.00", "total_amount": "98400.00",
      "billing_type": "ONE_TIME", "recurring_interval": null,
      "recurring_periods": 1
    }]
  },
  "can_confirm": true,
  "blocked_reason": null
}
```

When blocked, `blocked_reason` is a deliberately safe paraphrase — *"Your
requested changes are being reviewed by our team"* — never the margin, the
policy, or who is blocking it.

`DRAFT` versions are filtered out. **404** with
`details.reason = "not issued to your organization"` for another customer's
quote — 404 rather than 403 so ids cannot be enumerated.

### POST `/portal/quotes/{quote_id}/messages` — 201

| Field | Type | Required | Notes |
|---|---|---|---|
| `message_type` | `NegotiationMessageType` | no | Default `COMMENT`. `SELLER_REPLY`/`SYSTEM` rejected at validation |
| `body` | string | yes | 1–4000 |
| `quote_line_id` | uuid | no | Line-level comment |
| `lines[]` | `CounterOfferLine[]` | conditional | **Required** for `COUNTER_OFFER`/`CHANGE_REQUEST`; forbidden otherwise |

`CounterOfferLine`: `quote_line_id` plus at least one of
`requested_discount_pct` (0–100) / `requested_quantity` (> 0).

**201 counter-offer** — **VERIFIED**

```json
{
  "message": {
    "id": "…", "thread_id": "…", "quote_version_id": "…",
    "quote_line_id": null,
    "author_kind": "CUSTOMER", "author_display_name": "Casey Nolan",
    "message_type": "COUNTER_OFFER",
    "body": "We need 25% on the laptops to sign this quarter.",
    "requested_discount_pct": null, "requested_quantity": null,
    "requested_unit_price": null,
    "triggered_version_id": "…",
    "payload": {"requested_lines": [{"quote_line_id":"…","description":"Business Laptop",
                "current_discount_pct":"18.0000","requested_discount_pct":"25.0000",
                "current_quantity":"100.0000","requested_quantity":null}]},
    "created_at": "…"
  },
  "new_version_id": "…",
  "new_version_number": 2,
  "status": "PENDING_APPROVAL",
  "requires_reapproval": true,
  "customer_message": "Thank you — your requested changes have been captured as version 2 of this quote. Our team is reviewing the updated terms and you will be able to confirm once the review is complete."
}
```

`customer_message` is customer-safe prose; display it verbatim.

**Errors:** 409 `ALREADY_CONFIRMED`; 400 `EMPTY_COUNTER_OFFER`; 404 for a line
not on the current version.

### POST `/portal/quotes/{quote_id}/confirm`

Header: `Idempotency-Key: <uuid>` (strongly recommended).
Body: `{"acceptance_note": "optional, ≤2000"}`.

**200** — **VERIFIED**

```json
{
  "order": {
    "id": "…", "order_number": "SO-00001",
    "status": "CREATED", "currency": "USD", "payment_terms": "NET_30",
    "subtotal": "124310.00", "tax_amount": "0.00",
    "total_amount": "124310.00",
    "one_time_amount": "124010.00", "recurring_amount": "300.00",
    "confirmed_at": "…"
  },
  "message": "Order SO-00001 created.",
  "idempotent_replay": false
}
```

Replay returns the same body with `idempotent_replay: true` and
`message: "This quote was already confirmed; returning the existing order."`

**409 `STALE_APPROVAL`** — **VERIFIED**

```json
{
  "error": {
    "code": "STALE_APPROVAL",
    "message": "A material change invalidated the approval for this quote. It must be re-approved before it can be confirmed.",
    "details": {"quote_version_id":"…","version_number":2}
  }
}
```

**Full confirmation gate**, checked in this order:

| Code | HTTP | Condition |
|---|---|---|
| `ALREADY_CONFIRMED` | 409 | Version already confirmed |
| `VERSION_NOT_CONFIRMABLE` | 409 | `REJECTED` or `SUPERSEDED` |
| `STALE_APPROVAL` | 409 | `is_stale`, or latest request is `STALE` |
| `APPROVAL_REQUIRED` | 409 | No request, still `PENDING` (with `details.awaiting[]`), or not `APPROVED` |
| `VERSION_NOT_SENT` | 400 | Not `APPROVED`/`SENT`/`NEGOTIATING` |

### Seller side of the thread (internal roles)

`GET /quotes/{quote_id}/negotiation` → `NegotiationThreadRead` with all
messages. **404** if never sent.

`POST /quotes/{quote_id}/negotiation/reply` → 201 `NegotiationMessageRead`.
Body is a raw object: `{"body": "text"}`. Empty → 422 `VALIDATION_ERROR`.

---

## 13. Orders

### GET `/orders` — paginated **summary**

Filters: `status`, `customer_profile_id`, `has_backorder`,
`overdue_delivery`. Sortable: `confirmed_at` `created_at` `order_number`
`total_amount` `status`.

Returns `SalesOrderSummary` — **no lines, allocations or fulfillments**. Use
the detail route for those.

```json
{
  "items": [{
    "id": "…", "order_number": "SO-00001",
    "deal_id": "…", "quote_id": "…",
    "customer_profile_id": "…", "customer_name": "Acme Corporation",
    "status": "ALLOCATED", "currency": "USD", "payment_terms": "NET_30",
    "subtotal": "124310.00", "tax_amount": "0.00", "total_amount": "124310.00",
    "margin": "24110.00", "margin_pct": "19.3951",
    "one_time_amount": "124010.00", "recurring_amount": "300.00",
    "fully_allocated": true, "has_backorder": false,
    "promised_delivery_date": "2026-12-31",
    "is_delivery_late": false, "days_late": 0,
    "confirmed_at": "…", "allocated_at": "…", "fulfilled_at": null
  }],
  "total": 1, "limit": 25, "offset": 0
}
```

### GET `/orders/{order_id}` — full detail

`SalesOrderRead` — everything above plus `quote_version_id`,
`customer_organization_id`, `gross_revenue`, `total_discount`, `total_cost`,
`confirmed_by_user_id`, and three arrays:

- `lines[]` — `SalesOrderLineRead` with `quantity_allocated`, `quantity_backordered`, `quantity_fulfilled`, `promised_delivery_date`
- `allocations[]` — `AllocationRead`; `warehouse_name` reads `"Backorder (awaiting restock)"` when unsourced
- `fulfillments[]` — `FulfillmentRead` with carrier, tracking, `shipping_cost`, `shipped_at`, `delivered_at`

**403 for a portal user** — the full order shape exposes cost and margin, so
customers are refused here on purpose; their receipt comes from the confirm
response.

### POST `/orders/{order_id}/allocate` — `OPS` `SALES` `ADMIN`

Header: `Idempotency-Key`. Body:

| Field | Type | Notes |
|---|---|---|
| `overrides[]` | `ManualAllocationLine[]` | `{sales_order_line_id, warehouse_id, quantity}` — validated against real availability |
| `allow_partial` | bool | Default `true`. `false` fails the whole allocation if any line is short |

**200** — **VERIFIED**

```json
{
  "sales_order_id": "…",
  "status": "ALLOCATED",
  "fully_allocated": true,
  "has_backorder": false,
  "shipment_count": 2,
  "estimated_shipping_cost": "300.00",
  "lines": [{
    "sales_order_line_id": "…", "product_id": "…",
    "product_name": "Business Laptop",
    "quantity_requested": "100.0000",
    "quantity_allocated": "100.0000",
    "quantity_backordered": "0.0000",
    "splits": [
      {"warehouse_code":"MAIN","warehouse_name":"Main Warehouse","quantity":"60"},
      {"warehouse_code":"EAST","warehouse_name":"East Depot","quantity":"40"}
    ],
    "explanation": "Sourced 60 from Main Warehouse, 40 from East Depot; across 2 shipments because no single warehouse held all 100 units."
  }],
  "idempotent_replay": false,
  "message": "…"
}
```

`explanation` is per-line prose — display it beside the split so the
recommendation is defensible.

**Errors:** 409 `ORDER_CANCELLED`; 409 `INSUFFICIENT_INVENTORY`;
400 `OVERRIDE_EXCEEDS_LINE`; 404 for an override line not on the order.

### POST `/orders/{order_id}/fulfill` — `OPS` `ADMIN`

Body: `{"warehouse_id": null, "carrier": "DHL", "tracking_number": "TRK-1"}`.
Omit `warehouse_id` to ship everything. Returns the full `SalesOrderRead`.
One fulfilment per warehouse. **409 `NOTHING_TO_FULFILL`** if nothing is
allocated.

### PATCH `/orders/{order_id}/promise` — `SALES` `MANAGER` `ADMIN`

`{"promised_delivery_date": "2026-12-31"}` → 200. Slippage is measured against
this; without it there is nothing to compare.

### POST `/orders/{id}/fulfillments/{fid}/deliver` — `OPS` `ADMIN`

`{"delivered_at": null, "note": "optional"}` → 200 `SalesOrderRead`.
**Errors:** 409 `ALREADY_DELIVERED`, 409 `FULFILLMENT_NOT_SHIPPED`.

### POST `/orders/{order_id}/cancel` — `OPS` `ADMIN`

`{"reason": "required"}` → 200. Releases every reservation back to stock,
cancels uninvoiced schedules. **Errors:** 409 `ORDER_ALREADY_CANCELLED`,
409 `ORDER_ALREADY_SHIPPED`.

---

## 14. Billing

### GET `/billing/schedules` — bare array

Filters: `sales_order_id`, `billing_type`. **VERIFIED** (one item)

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "schedule_number": "SO-00001-R1",
  "sales_order_id": "…", "sales_order_line_id": "…",
  "billing_type": "RECURRING", "recurring_interval": "YEARLY",
  "status": "SCHEDULED", "currency": "USD",
  "amount": "300.00", "tax_amount": "0.00", "total_amount": "300.00",
  "period_number": 1, "total_periods": 1,
  "period_start": "2026-09-05", "period_end": "2027-09-04",
  "due_date": "2026-10-05",
  "is_prorated": false, "proration_factor": "1.00000000",
  "description": "Annual Support Plan — period 1",
  "detail": {"quantity":"1.0000","unit_net_price":"300.0000",
             "category":"SUBSCRIPTION","interval_months":12}
}
```

`SUM(amount)` for a line equals that line's `net_amount` **exactly** for any
period count — the final period absorbs the remainder.

### GET `/billing/orders/{order_id}/summary` — **VERIFIED**

```json
{
  "sales_order_id": "…",
  "one_time_total": "124010.00",
  "recurring_total_per_year": "300.00",
  "recurring_contract_total": "300.00",
  "grand_total": "124310.00",
  "schedule_count": 4,
  "one_time_count": "3",
  "recurring_count": "1"
}
```

### GET `/billing/proration-preview` — **VERIFIED**

Query: `full_period_amount` (> 0), `period_start`, `period_end`, `billed_from`.

```json
{
  "full_period_amount": "1200.00",
  "days_in_period": 365,
  "days_billed": 184,
  "proration_factor": "0.50410959",
  "prorated_amount": "604.93",
  "explanation": "Billing starts 2026-07-01 inside the period 2026-01-01 to 2026-12-31 (184 of 365 days), so 1200.00 is prorated to 604.93."
}
```

Both endpoints of the period are inclusive.
**Errors:** 400 `INVALID_PERIOD`, 400 `INVALID_PRORATION`.

### Invoices and payments — `FINANCE` `ADMIN` for writes

| Method | Path | Notes |
|---|---|---|
| GET | `/billing/invoices` | Bare array |
| POST | `/billing/invoices` | 201. `{billing_schedule_id, issue_date?}` |
| POST | `/billing/invoices/{invoice_id}/payments` | 201 `PaymentRead` |
| POST | `/billing/invoices/{invoice_id}/void` | 200. `{reason}` |

**`InvoiceRead`** — **VERIFIED**

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "invoice_number": "INV-00001",
  "sales_order_id": "…", "billing_schedule_id": "…",
  "status": "PAID", "currency": "USD",
  "subtotal": "300.00", "tax_amount": "0.00", "total_amount": "300.00",
  "amount_paid": "300.00", "amount_due": "0.00",
  "issue_date": "2026-09-05", "due_date": "2026-10-05",
  "paid_at": "…",
  "is_overdue": false, "days_overdue": 0
}
```

`is_overdue`/`days_overdue` are **computed on read** — there is no scheduler,
so a stored flag would be stale.

Payment recording drives the status: `amount_paid >= total` → `PAID` (and the
linked schedule → `COMPLETED`); otherwise `PARTIALLY_PAID`.

**Errors:** 409 `SCHEDULE_ALREADY_INVOICED`; 409 `INVOICE_VOID`;
400 `OVERPAYMENT` with `details.amount_due`; 409 `INVOICE_PART_PAID` on void.

### Subscription lifecycle — `FINANCE` `ADMIN`

**POST `/billing/subscriptions/{schedule_id}/change`**

| Field | Type | Notes |
|---|---|---|
| `new_quantity` | decimal | > 0 |
| `new_interval` | `RecurringInterval` | |
| `effective_date` | date | Defaults today; must fall inside the period |
| `reason` | string | ≤ 2000 |

At least one of quantity/interval required → 422.

**POST `/billing/subscriptions/{schedule_id}/cancel`**
`{"effective_date": …, "reason": …}`

Both return `SubscriptionChangeResponse` — 🔍 **INFERRED FROM CODE**
(asserted by `tests/test_subscription_lifecycle.py`):

```json
{
  "change_type": "CANCELLATION",
  "sales_order_line_id": "…",
  "effective_date": "2026-03-05",
  "periods_kept": 1, "periods_regenerated": 0,
  "previous_period_amount": "300.00",
  "new_period_amount": "148.77",
  "proration_credit": "151.23",
  "proration_charge": "0.00",
  "credit_note_id": "…",
  "schedules": [{"schedule_number":"SO-00001-R1","period_number":1,
                 "status":"CANCELLED","amount":"148.77",
                 "period_start":"2026-09-05","period_end":"2027-09-04"}],
  "explanation": "'Annual Support Plan' cancelled effective 2026-03-05. 148.77 of the 300.00 period was consumed; 151.23 was unused and 0 later period(s) were cancelled. A credit note for 151.23 was issued."
}
```

**Errors:** 409 `PERIOD_ALREADY_INVOICED` (invoiced periods are immutable);
400 `SUBSCRIPTION_NOT_RECURRING`; 400 `EFFECTIVE_DATE_OUTSIDE_PERIOD`;
409 `SCHEDULE_ALREADY_CANCELLED`.

### Credit notes

| Method | Path | Auth |
|---|---|---|
| GET | `/billing/credit-notes` | internal. Filters: `sales_order_id`, `status` |
| GET | `/billing/credit-notes/{credit_note_id}` | internal |
| POST | `/billing/credit-notes/{id}/refund` | `FINANCE` `ADMIN`. `{amount?}` — omit for the full balance |
| POST | `/billing/credit-notes/{id}/void` | `FINANCE` `ADMIN`. `{reason}` |

**`CreditNoteRead`** — 🔍 **INFERRED FROM CODE**

```json
{
  "id": "…", "created_at": "…", "updated_at": "…",
  "credit_note_number": "CN-00001",
  "sales_order_id": "…", "invoice_id": "…", "billing_schedule_id": "…",
  "customer_organization_id": "…",
  "status": "ISSUED", "reason": "SUBSCRIPTION_CANCELLED",
  "reason_note": "Cancellation of 'Annual Support Plan' effective 2026-03-05.",
  "currency": "USD",
  "subtotal": "151.23", "tax_amount": "0.00", "total_amount": "151.23",
  "amount_refunded": "0.00", "amount_outstanding": "151.23",
  "issue_date": "2026-09-05", "issued_by_user_id": "…", "voided_at": null,
  "detail": {"period_amount":"300.00","consumed_amount":"148.77",
             "unused_current_period":"151.23","proration":"…"}
}
```

Refunding records a `Payment` with status `REFUNDED` against the invoice.
**Errors:** 400 `REFUND_EXCEEDS_CREDIT`; 400 `INVALID_REFUND_AMOUNT`;
409 `CREDIT_NOTE_VOID`; 409 `CREDIT_NOTE_PARTLY_REFUNDED` on void.

---

## 15. Dashboard and audit (all internal roles)

### GET `/dashboard/control-tower` — **VERIFIED**

```json
{
  "organization_id": "…",
  "generated_at": "…",
  "counts": {"critical":0,"high":0,"medium":0,"low":0,"total_open":0},
  "by_type": {},
  "groups": [],
  "my_queue": [],
  "headline": "Nothing needs your attention. Every deal is inside policy."
}
```

With work outstanding, `groups[]` holds `{severity, count, items[]}`
severity-sorted, and `my_queue[]` holds items owned by the caller's role.
`headline` is display-ready prose.

### GET `/dashboard/attention-items` — paginated

Filters: `severity`, `type`, `include_resolved`, `owner_role`, `mine`.

**`AttentionItemRead`** — **VERIFIED**

```json
{
  "id": "…", "source_type": "approval_request", "source_id": "…",
  "type": "STALE_APPROVAL", "severity": "CRITICAL",
  "title": "Approval invalidated on Q-00001 v2",
  "reason": "Approval of version 1 is no longer valid: …",
  "impact": "The order for Acme Corporation cannot proceed: confirmation is blocked …",
  "owner_role": "FINANCE", "owner_user_id": null,
  "recommended_action": "Review revised quote Q-00001 v2 and either re-approve it or request a further revision.",
  "status": "OPEN",
  "deal_id": "…", "quote_id": "…",
  "detail": {"quote_version_id":"…"},
  "created_at": "…", "resolved_at": null,
  "acknowledged_at": null, "acknowledged_by_user_id": null,
  "nudge_count": 0, "last_nudged_at": null,
  "escalated_at": null, "escalation_note": null
}
```

Every item answers four questions — **why** (`reason`), **impact**,
**owner** (`owner_role`), **what next** (`recommended_action`).

### Attention-item actions

| Method | Path | Body | Auth |
|---|---|---|---|
| POST | `…/{item_id}/resolve` | `{resolution_note?}` | Owner role, assignee, or `ADMIN` |
| POST | `…/{item_id}/acknowledge` | `{note?}` | Owner role, assignee, or `ADMIN` |
| POST | `…/{item_id}/nudge` | `{note?}` | **Any internal role** |
| POST | `…/{item_id}/escalate` | `{note, owner_role?}` | Any internal role |

`resolve` and `acknowledge` return `AttentionItemRead`. `nudge` returns:

```json
{
  "item": { },
  "message": "MANAGER has been nudged about 'Quote Q-00001 awaiting approval' (1 time(s) so far).",
  "notified_role": "MANAGER",
  "nudge_count": 1
}
```

`escalate` raises severity one band and optionally reassigns `owner_role`.

**403 `NOT_ITEM_OWNER`** on resolve/acknowledge by a non-owner:

```json
{"error":{"code":"NOT_ITEM_OWNER","message":"Only MANAGER or ADMIN may resolve this item.","details":{"owner_role":"MANAGER","your_role":"SALES","action":"resolve"}}}
```

**409 `ITEM_ALREADY_RESOLVED`** for any action on a resolved item.

### GET `/dashboard/deal-health` — **VERIFIED**

```json
{
  "generated_at": "…",
  "average_health": 100,
  "deals": [{
    "deal_id": "…", "deal_reference": "D-00001",
    "deal_name": "Acme Q1 laptop refresh",
    "customer_name": "Acme Corporation",
    "stage": "CLOSED_WON",
    "health_score": 100, "health_band": "HEALTHY",
    "total_value": "124310.00", "margin_pct": "19.3951",
    "blocked": false,
    "signals": [{"code":"HEALTHY","label":"On track","severity":"LOW",
                 "detail":"No policy breaches, no blockers, no stale decisions.",
                 "points":0}],
    "open_attention_items": 0,
    "summary": "…"
  }]
}
```

Bands: ≥80 `HEALTHY`, ≥60 `WATCH`, ≥40 `AT_RISK`, else `CRITICAL`.
`signals[]` carries **every deduction with its point value** — render the
arithmetic, not just the score.

`GET /dashboard/deal-health/{deal_id}` returns a single `DealHealthRead`.

### GET `/audit/events` — paginated

Filters: `entity_type`, `entity_id`, `event_type`, `actor_user_id`,
`newest_first` (default false — sequence order is story order).

**`AuditEventRead`** — **VERIFIED**

```json
{
  "id": "…", "sequence": 4,
  "event_type": "USER_LOGGED_IN",
  "entity_type": "user", "entity_id": "…",
  "actor_user_id": "…", "actor_email": "admin@techsupply.com",
  "actor_role": "ADMIN",
  "payload": {"role": "ADMIN"},
  "occurred_at": "…"
}
```

`sequence` is a monotonic bigint — a single transaction emits several events in
the same microsecond, so order by `sequence`, never by timestamp. Money in
`payload` is always a string.

### GET `/audit/quotes/{quote_id}/timeline` — bare array

The whole story in one call: quote, all versions, all approval requests, all
orders and negotiation messages, ordered by `sequence`. The canonical flow
produces 22 events.

**37 event types:** `USER_SIGNED_UP` `USER_LOGGED_IN` `QUOTE_CREATED`
`QUOTE_CALCULATED` `QUOTE_SUBMITTED` `POLICY_EVALUATED` `APPROVAL_REQUESTED`
`APPROVAL_GRANTED` `APPROVAL_REJECTED` `APPROVAL_REVISION_REQUESTED`
`APPROVAL_MARKED_STALE` `QUOTE_APPROVED` `QUOTE_SENT` `CUSTOMER_COUNTERED`
`CUSTOMER_COMMENTED` `QUOTE_REVISED` `MATERIAL_CHANGE_DETECTED`
`QUOTE_CONFIRMED` `QUOTE_LOST` `ORDER_CREATED` `INVENTORY_ALLOCATED`
`INVENTORY_SHORTAGE` `ORDER_FULFILLED` `ORDER_DELIVERED` `ORDER_CANCELLED`
`BILLING_SCHEDULED` `SUBSCRIPTION_CHANGED` `SUBSCRIPTION_CANCELLED`
`CREDIT_NOTE_ISSUED` `CREDIT_NOTE_REFUNDED` `CREDIT_NOTE_VOIDED`
`INVOICE_ISSUED` `INVOICE_VOIDED` `PAYMENT_RECORDED`
`ATTENTION_ITEM_CREATED` `ATTENTION_ITEM_RESOLVED`
`ATTENTION_ITEM_ACKNOWLEDGED` `ATTENTION_ITEM_NUDGED`
`ATTENTION_ITEM_ESCALATED`

---

## 16. Reports (all internal roles)

Every report accepts the period filter plus `rep_user_id`, `team_id`,
`approval_status`, `product_id`, `category`, `customer_profile_id`, and echoes
the applied filters so an export is self-describing.

| Path | Content |
|---|---|
| `/reports/sales-performance` | Revenue, margin, discount, win rate. `group_by` = `rep` `customer` `tier` `stage` `status` `month` `risk_band` |
| `/reports/approval-status` | Counts, value and time-to-decision per state |
| `/reports/products` | `best_selling`, `most_discounted`, `highest_margin_contribution` |
| `/reports/discounts` | Per-rep distribution plus a band histogram |
| `/reports/pipeline` | Deal count and value by stage, win rate |
| `/reports/discount-anomalies` | Quotes discounted above the rep's own average |

### GET `/reports/sales-performance` — **VERIFIED**

```json
{
  "group_by": "rep",
  "filters": {"period":"All time","date_from":null,"date_to":null,
              "rep_user_id":null,"team_id":null,"approval_status":null,
              "product_id":null,"category":null,"customer_profile_id":null},
  "rows": [{
    "group_key": "10b3c1ca-…", "group_label": "Sam Rivera",
    "quote_count": 1, "version_count": 2,
    "gross_revenue": "321600.00", "total_discount": "64580.00",
    "net_revenue": "257020.00", "total_cost": "200400.00",
    "margin": "56620.00", "margin_pct": "22.0294",
    "avg_discount_pct": "20.0809", "avg_blended_risk": "37.1390",
    "won_count": 1, "lost_count": 0, "win_rate_pct": "100.0000"
  }],
  "totals": {
    "quote_count": 1,
    "gross_revenue": "321600.00", "total_discount": "64580.00",
    "net_revenue": "257020.00", "total_cost": "200400.00",
    "margin": "56620.00", "margin_pct": "22.0294",
    "effective_discount_pct": "20.0809",
    "won_count": 1, "lost_count": 0, "win_rate_pct": "100.0000"
  }
}
```

Measured over **quote versions**, so a discounted deal that was lost is
counted — restricting to orders would hide exactly the losses a discount
report exists to surface.

### GET `/reports/discount-anomalies` — **VERIFIED**

```json
{
  "generated_at": "…",
  "anomaly_count": 0,
  "items": [{
    "quote_id": "…", "quote_version_id": "…",
    "quote_number": "Q-00001", "version_number": 2,
    "customer_name": "Acme Corporation",
    "rep_user_id": "…", "rep_name": "Sam Rivera",
    "is_anomaly": false,
    "effective_discount_pct": "22.6928",
    "sigma_threshold": "2.0000",
    "deviations_above_mean": "0.0000",
    "trigger_at_pct": "0.0000",
    "severity": "LOW",
    "reason": "No anomaly check performed: Sam Rivera has 1 prior quote(s), and 5 are required before a personal baseline is statistically meaningful.",
    "baseline": {"user_id":"…","sample_count":1,"mean_discount_pct":"17.4689",
                 "stdev":"0.0000","min_discount_pct":"17.4689",
                 "max_discount_pct":"17.4689","is_reliable":false,
                 "min_samples_required":5},
    "created_at": "…"
  }]
}
```

Query `include_normal=true` to see checked-and-normal versions.
`reason` always states the arithmetic, including why a check was skipped.

### GET `/reports/{report_name}/export` — **binary**

`format` = `csv` | `xlsx` | `pdf` (default `xlsx`).

The **only non-JSON responses in the API**:

| Format | `Content-Type` |
|---|---|
| `csv` | `text/csv; charset=utf-8` (UTF-8 BOM so Excel opens it correctly) |
| `xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `pdf` | `application/pdf` |

Also sends `Content-Disposition: attachment; filename="dealflow360-<report>-<timestamp>.<ext>"`,
plus `X-Export-Format` and `X-Export-Rows`. All three are CORS-exposed.

Handle in the browser with a blob download, not `res.json()`:

```ts
const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
const blob = await res.blob();
```

**Errors:** 400 `UNSUPPORTED_EXPORT_FORMAT`; 400
`EXPORT_DEPENDENCY_MISSING` with `details.package` if `openpyxl`/`reportlab`
is absent.

`GET /reports/export/formats` advertises capability:

```json
{"formats":["csv","xlsx","pdf"],"default":"xlsx",
 "reports":["sales-performance","approval-status","products","discounts","pipeline"]}
```

---

## 17. Complete error code reference

### By status

| HTTP | Codes |
|---|---|
| **400** | `BUSINESS_RULE_VIOLATION` `ORGANIZATION_REQUIRED` `ROLE_ORG_MISMATCH` `CUSTOMER_ORGANIZATION_REQUIRED` `ORGANIZATION_NOT_CUSTOMER` `EMPTY_QUOTE` `EMPTY_REVISION` `EMPTY_COUNTER_OFFER` `EMPTY_SUBSCRIPTION_CHANGE` `OVERPAYMENT` `OVERRIDE_EXCEEDS_LINE` `VERSION_NOT_SENT` `INVALID_PERIOD` `INVALID_PRORATION` `INVALID_PERIOD_COUNT` `SUBSCRIPTION_NOT_RECURRING` `EFFECTIVE_DATE_OUTSIDE_PERIOD` `INVALID_SUBSCRIPTION_QUANTITY` `REFUND_EXCEEDS_CREDIT` `INVALID_REFUND_AMOUNT` `VARIANT_PRODUCT_MISMATCH` `EXTERNAL_USER_NOT_ELIGIBLE` `UNSUPPORTED_EXPORT_FORMAT` `EXPORT_DEPENDENCY_MISSING` |
| **401** | `AUTHENTICATION_FAILED` `WRONG_TOKEN_TYPE` `USER_DISABLED` `ORGANIZATION_DISABLED` |
| **403** | `FORBIDDEN` `PORTAL_USER_FORBIDDEN` `INTERNAL_USER_FORBIDDEN` `SELF_APPROVAL_FORBIDDEN` `WRONG_APPROVER_ROLE` `NOT_ITEM_OWNER` |
| **404** | `NOT_FOUND` (also used for every cross-tenant access) |
| **405** | `METHOD_NOT_ALLOWED` |
| **409** | `CONFLICT` `IMMUTABLE_VERSION` `VERSION_TERMINAL` `VERSION_NOT_DRAFT` `VERSION_NOT_APPROVED` `VERSION_NOT_CONFIRMABLE` `STALE_APPROVAL` `APPROVAL_REQUIRED` `APPROVAL_NOT_PENDING` `NO_PENDING_STEP` `ALREADY_CONFIRMED` `DUPLICATE_OPERATION` `IDEMPOTENCY_KEY_REUSED` `IDEMPOTENT_REQUEST_IN_FLIGHT` `INSUFFICIENT_INVENTORY` `STOCK_BELOW_RESERVED` `STOCK_NEGATIVE` `NOTHING_TO_FULFILL` `ORDER_CANCELLED` `ORDER_ALREADY_CANCELLED` `ORDER_ALREADY_SHIPPED` `ALREADY_DELIVERED` `FULFILLMENT_NOT_SHIPPED` `EMAIL_ALREADY_REGISTERED` `SKU_EXISTS` `WAREHOUSE_CODE_EXISTS` `POLICY_CODE_EXISTS` `SALES_TEAM_CODE_EXISTS` `CUSTOMER_PROFILE_EXISTS` `SCHEDULE_ALREADY_INVOICED` `SCHEDULE_ALREADY_CANCELLED` `PERIOD_ALREADY_INVOICED` `INVOICE_VOID` `INVOICE_PART_PAID` `CREDIT_NOTE_VOID` `CREDIT_NOTE_PARTLY_REFUNDED` `QUOTE_ALREADY_LOST` `QUOTE_ALREADY_CONFIRMED` `ITEM_ALREADY_RESOLVED` |
| **422** | `VALIDATION_ERROR` `INVALID_SORT_FIELD` `INVALID_GROUP_BY` `PERIOD_RANGE_REQUIRED` `INVALID_PERIOD_RANGE` `UNKNOWN_REPORT` |
| **429** | `RATE_LIMITED` |
| **500** | `INTERNAL_ERROR` |

### Codes never returned

`TENANT_ISOLATION` is defined in [`app/errors.py`](../app/errors.py) but never
raised — cross-tenant access returns 404 instead, so a response code cannot be
used to probe which ids exist in other organizations.

---

## 18. Enumerations

Every enum is stored as `VARCHAR` with a CHECK constraint and crosses the wire
as its exact uppercase string.

| Enum | Values |
|---|---|
| `OrganizationKind` | `SELLER` `CUSTOMER` |
| `RoleCode` | `SALES` `MANAGER` `FINANCE` `OPS` `CUSTOMER` `ADMIN` |
| `CustomerTier` | `BRONZE` `SILVER` `GOLD` `PLATINUM` |
| `PaymentTerms` | `PREPAID` `NET_15` `NET_30` `NET_45` `NET_60` `NET_90` |
| `ProductCategory` | `HARDWARE` `SOFTWARE` `SERVICE` `SUBSCRIPTION` |
| `BillingType` | `ONE_TIME` `RECURRING` |
| `RecurringInterval` | `MONTHLY` `QUARTERLY` `YEARLY` |
| `DealStage` | `QUALIFICATION` `PROPOSAL` `NEGOTIATION` `CLOSED_WON` `CLOSED_LOST` |
| `QuoteStatus` | `OPEN` `CONFIRMED` `LOST` `CANCELLED` |
| `QuoteVersionStatus` | `DRAFT` `PENDING_APPROVAL` `APPROVED` `SENT` `NEGOTIATING` `CONFIRMED` `REJECTED` `SUPERSEDED` |
| `QuoteVersionSource` | `INITIAL` `INTERNAL_REVISION` `CUSTOMER_COUNTER` `APPROVER_REVISION_REQUEST` |
| `PolicyType` | `CATEGORY_DISCOUNT_CEILING` `MIN_MARGIN` `DISCOUNT_AMOUNT_AUTHORITY` `PAYMENT_TERMS_LIMIT` |
| `PolicyComparison` | `LTE` `GTE` |
| `PolicyUnit` | `PERCENT` `AMOUNT` `DAYS` |
| `PolicyResultStatus` | `PASSED` `WARNING` `VIOLATED` `NOT_APPLICABLE` |
| `RiskBand` | `NONE` `LOW` `MEDIUM` `HIGH` `CRITICAL` |
| `ApprovalLevel` | `SALES_MANAGER` `FINANCE` `EXECUTIVE` |
| `ApprovalRequestStatus` | `PENDING` `APPROVED` `REJECTED` `REVISION_REQUESTED` `STALE` `CANCELLED` |
| `ApprovalStepStatus` | `PENDING` `APPROVED` `REJECTED` `REVISION_REQUESTED` `SKIPPED` `STALE` |
| `ApprovalDecisionType` | `APPROVE` `REJECT` `REQUEST_REVISION` |
| `Severity` | `LOW` `MEDIUM` `HIGH` `CRITICAL` |
| `AttentionItemType` | `STALE_APPROVAL` `MARGIN_VIOLATION` `PENDING_APPROVAL` `INVENTORY_SHORTAGE` `CUSTOMER_RESPONSE_REQUIRED` `ORDER_BLOCKED` `DISCOUNT_ANOMALY` `DELIVERY_SLIPPAGE` `STALLED_DEAL` `APPROVAL_SLA_BREACH` `INVENTORY_REORDER_NEEDED` |
| `AttentionItemStatus` | `OPEN` `ACKNOWLEDGED` `RESOLVED` |
| `NegotiationThreadStatus` | `OPEN` `AWAITING_SELLER` `AWAITING_CUSTOMER` `RESOLVED` `CLOSED` |
| `NegotiationMessageType` | `COMMENT` `QUESTION` `CHANGE_REQUEST` `COUNTER_OFFER` `SELLER_REPLY` `SYSTEM` |
| `AuthorKind` | `CUSTOMER` `SELLER` `SYSTEM` |
| `SalesOrderStatus` | `CREATED` `ALLOCATED` `PARTIALLY_ALLOCATED` `BACKORDERED` `PARTIALLY_FULFILLED` `FULFILLED` `CANCELLED` |
| `AllocationStatus` | `RESERVED` `ALLOCATED` `BACKORDERED` `SHIPPED` `RELEASED` `CANCELLED` |
| `AllocationMode` | `AUTOMATIC` `MANUAL_OVERRIDE` |
| `FulfillmentStatus` | `PENDING` `PICKED` `SHIPPED` `DELIVERED` `CANCELLED` |
| `BillingScheduleStatus` | `SCHEDULED` `ACTIVE` `INVOICED` `COMPLETED` `CANCELLED` |
| `InvoiceStatus` | `DRAFT` `ISSUED` `PARTIALLY_PAID` `PAID` `OVERDUE` `VOID` |
| `PaymentMethod` | `BANK_TRANSFER` `CARD` `CHECK` `ACH` `OTHER` |
| `PaymentStatus` | `PENDING` `SETTLED` `FAILED` `REFUNDED` |
| `CreditNoteStatus` | `DRAFT` `ISSUED` `APPLIED` `VOID` |
| `CreditNoteReason` | `SUBSCRIPTION_CANCELLED` `SUBSCRIPTION_DOWNGRADED` `ORDER_CANCELLED` `BILLING_CORRECTION` `GOODWILL` |
| `SubscriptionChangeType` | `QUANTITY` `INTERVAL` `CANCELLATION` |
| `IdempotencyStatus` | `IN_PROGRESS` `COMPLETED` `FAILED` |

Some values are not reachable through any endpoint — see
[`ENTITY_STATE_LIFECYCLES.md`](./ENTITY_STATE_LIFECYCLES.md) §15 before building UI for them.

---

## 19. Capabilities the backend does not have

Confirmed absent by source inspection. Do not build UI for these.

| Capability | Status |
|---|---|
| WebSockets / SSE / long-poll | ❌ **NOT IMPLEMENTED**. No `WebSocket`, `EventSource` or `text/event-stream` anywhere. "Real time" means recomputed-on-read; use refetch-on-action plus optional polling |
| File upload | ❌ **NOT IMPLEMENTED**. No `UploadFile` or `multipart` handler |
| File download other than report export | ❌ **NOT IMPLEMENTED** |
| Customer-facing PDF quote | ❌ **NOT IMPLEMENTED** by design — the portal replaces the static PDF |
| Background jobs / scheduler | ❌ **NOT IMPLEMENTED**. Overdue and stalled states are computed on read |
| Notifications (email / push / in-app store) | ❌ **NOT IMPLEMENTED**. `nudge` records and audits an intent; it does not deliver a message |
| Bulk / batch mutation | ❌ **NOT IMPLEMENTED** |
| Soft delete / restore | ❌ **NOT IMPLEMENTED**. Deactivation via `is_active` where available |
| Multi-currency conversion | ❌ **NOT IMPLEMENTED**. Currency is stored per quote/order; no FX |
| Full-text search | ❌ **NOT IMPLEMENTED**. `q` parameters are `ILIKE` substring matches |
| GraphQL | ❌ **NOT IMPLEMENTED** |
| API versioning | ❌ Not present. `API_PREFIX` is empty and configurable |
