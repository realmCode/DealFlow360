# ROLE PERMISSION MATRIX

Derived by reading every route in [`app/routers/`](../app/routers/) and the
dependency definitions in [`app/dependencies.py`](../app/dependencies.py).
Verified against the live server at `http://127.0.0.1:8000` for the auth and
RBAC cases (see §5).

Legend:

| Symbol | Meaning |
|---|---|
| Y | Permitted |
| — | Denied (403) |
| 404 | Denied via 404 rather than 403, to prevent id enumeration |
| n/a | Route is not reachable by this role at all |

---

## 1. Dependency reference

| Dependency | Roles accepted | Error on failure |
|---|---|---|
| *(none)* | Unauthenticated | — |
| `CurrentUser` | Any authenticated user | 401 `AUTHENTICATION_FAILED` |
| `InternalUser` | `SALES` `MANAGER` `FINANCE` `OPS` `ADMIN` | 403 `PORTAL_USER_FORBIDDEN` |
| `CustomerUser` | `CUSTOMER` | 403 `INTERNAL_USER_FORBIDDEN` |
| `SalesUser` | `SALES` `MANAGER` `ADMIN` | 403 `FORBIDDEN` + `allowed_roles` |
| `ApproverUser` | `MANAGER` `FINANCE` `ADMIN` | 403 `FORBIDDEN` + `allowed_roles` |
| `AdminUser` | `ADMIN` | 403 `FORBIDDEN` + `allowed_roles` |
| `OpsUser` | `OPS` `ADMIN` | **Defined but unused** — see §4 |

Inline handler-body checks (not declared dependencies, so invisible to OpenAPI):

| Route | Inline restriction |
|---|---|
| `POST /orders/{id}/allocate` | `OPS` `ADMIN` `SALES` |
| `POST /orders/{id}/fulfill` | `OPS` `ADMIN` |
| `POST /billing/invoices` | `FINANCE` `ADMIN` |
| `POST /billing/invoices/{id}/payments` | `FINANCE` `ADMIN` |
| `GET /orders/{id}` | Explicitly rejects `CUSTOMER` with `PORTAL_USER_FORBIDDEN` |

---

## 2. Feature-level matrix

| Feature | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|
| Sign up / log in / refresh | Y | Y | Y | Y | Y | Y | Y |
| View own profile | — | Y | Y | Y | Y | Y | Y |
| List / create users | — | — | — | — | — | Y | — |
| Configure catalog (products, variants, price lists) | — | — | — | — | — | Y | — |
| Configure warehouses and stock | — | — | — | — | — | Y | — |
| Configure policies (discount tiers, approval chains) | — | — | — | — | — | Y | — |
| Load seed dataset | — | — | — | — | — | Y | — |
| Read catalog and policies | — | Y | Y | Y | Y | Y | — |
| Read warehouses and inventory | — | Y | Y | Y | Y | Y | — |
| Read customers and contacts | — | Y | Y | Y | Y | Y | — |
| Create / update customers and contacts | — | Y | Y | — | — | Y | — |
| Read deals | — | Y | Y | Y | Y | Y | — |
| Create / update deals | — | Y | Y | — | — | Y | — |
| Create quotes | — | Y | Y | — | — | Y | — |
| Read quotes and versions (with cost/margin/risk) | — | Y | Y | Y | Y | Y | — |
| Add / edit / delete quote lines (`DRAFT` only) | — | Y | Y | — | — | Y | — |
| Recalculate a version | — | Y | Y | Y | Y | Y | — |
| Read policy results and blended risk | — | Y | Y | Y | Y | Y | — |
| Submit for approval | — | Y | Y | — | — | Y | — |
| Read Decision Fabric impact | — | Y | Y | Y | Y | Y | — |
| Create a revision | — | Y | Y | — | — | Y | — |
| Send to customer portal | — | Y | Y | — | — | Y | — |
| Read upsell / cross-sell recommendations | — | Y | Y | Y | Y | Y | — |
| **Approval inbox** | — | — | Y | Y | — | Y | — |
| Read an approval request | — | Y | Y | Y | Y | Y | — |
| **Approve / reject / return for revision** | — | — | Y | Y | — | Y | — |
| Approve own authored quote | — | — | — | — | — | — | — |
| **Portal: list and read own quotes** | — | — | — | — | — | — | Y |
| **Portal: post message / counter-offer** | — | — | — | — | — | — | Y |
| **Portal: confirm quote** | — | — | — | — | — | — | Y |
| Read negotiation thread (seller side) | — | Y | Y | Y | Y | Y | — |
| Reply in negotiation thread | — | Y | Y | Y | Y | Y | — |
| Read orders | — | Y | Y | Y | Y | Y | — |
| **Allocate stock** | — | Y | — | — | Y | Y | — |
| **Fulfil order** | — | — | — | — | Y | Y | — |
| Read allocations | — | Y | Y | Y | Y | Y | — |
| Read billing schedules and summary | — | Y | Y | Y | Y | Y | — |
| Proration preview | — | Y | Y | Y | Y | Y | — |
| Read invoices | — | Y | Y | Y | Y | Y | — |
| **Issue invoices** | — | — | — | Y | — | Y | — |
| **Record payments** | — | — | — | Y | — | Y | — |
| Control Tower and attention items | — | Y | Y | Y | Y | Y | — |
| Resolve an attention item | — | Y | Y | Y | Y | Y | — |
| Deal health dashboard | — | Y | Y | Y | Y | Y | — |
| Audit trail and quote timeline | — | Y | Y | Y | Y | Y | — |
| See cost, margin, internal risk | — | Y | Y | Y | Y | Y | **Never** |
| Access another organization's data | — | 404 | 404 | 404 | 404 | 404 | 404 |

---

## 3. Endpoint-level matrix

All 78 operations. Prefix is empty (`api_prefix = ""`).

### System

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/` | none | Y | Y | Y | Y | Y | Y | Y |
| GET | `/health` | none | Y | Y | Y | Y | Y | Y | Y |
| GET | `/docs` `/redoc` `/openapi.json` | none | Y | Y | Y | Y | Y | Y | Y |

### Auth and users

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| POST | `/auth/signup` | none | Y | Y | Y | Y | Y | Y | Y |
| POST | `/auth/login` | none | Y | Y | Y | Y | Y | Y | Y |
| POST | `/auth/refresh` | none | Y | Y | Y | Y | Y | Y | Y |
| GET | `/users/me` | `CurrentUser` | — | Y | Y | Y | Y | Y | Y |
| GET | `/users` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/users` | `AdminUser` | — | — | — | — | — | Y | — |

### Admin configuration

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| POST | `/admin/products` | `AdminUser` | — | — | — | — | — | Y | — |
| PATCH | `/admin/products/{product_id}` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/warehouses` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/inventory` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/inventory/adjust` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/policies` | `AdminUser` | — | — | — | — | — | Y | — |
| PATCH | `/admin/policies/{policy_id}` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/product-variants` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/price-lists` | `AdminUser` | — | — | — | — | — | Y | — |
| POST | `/admin/seed` | `AdminUser` | — | — | — | — | — | Y | — |

### Catalog, policies, inventory (read)

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/products` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/products/{product_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/policies` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/policies/{policy_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/warehouses` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/inventory` | `InternalUser` | — | Y | Y | Y | Y | Y | — |

### Customers

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/customers` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/customers` | `SalesUser` | — | Y | Y | — | — | Y | — |
| GET | `/customers/{customer_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| PATCH | `/customers/{customer_id}` | `SalesUser` | — | Y | Y | — | — | Y | — |
| GET | `/customers/{customer_id}/contacts` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/customers/{customer_id}/contacts` | `SalesUser` | — | Y | Y | — | — | Y | — |

### Deals and quotes

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/deals` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/deals` | `SalesUser` | — | Y | Y | — | — | Y | — |
| GET | `/deals/{deal_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| PATCH | `/deals/{deal_id}` | `SalesUser` | — | Y | Y | — | — | Y | — |
| POST | `/deals/{deal_id}/quotes` | `SalesUser` | — | Y | Y | — | — | Y | — |
| GET | `/quotes/{quote_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/quote-versions/{version_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/quote-versions/{version_id}/lines` | `SalesUser` | — | Y | Y | — | — | Y | — |
| PATCH | `/quote-versions/{v}/lines/{line_id}` | `SalesUser` | — | Y | Y | — | — | Y | — |
| DELETE | `/quote-versions/{v}/lines/{line_id}` | `SalesUser` | — | Y | Y | — | — | Y | — |
| POST | `/quote-versions/{v}/calculate` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/quote-versions/{v}/policy-results` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/quote-versions/{v}/submit` | `SalesUser` | — | Y | Y | — | — | Y | — |
| GET | `/quote-versions/{v}/impact` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/quote-versions/{v}/revisions` | `SalesUser` | — | Y | Y | — | — | Y | — |
| POST | `/quote-versions/{v}/send` | `SalesUser` | — | Y | Y | — | — | Y | — |
| GET | `/quotes/{quote_id}/recommendations` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/quote-versions/{v}/approval` | `InternalUser` | — | Y | Y | Y | Y | Y | — |

### Approvals

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/approvals/inbox` | `ApproverUser` | — | — | Y | Y | — | Y | — |
| GET | `/approvals/{request_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/approvals/{request_id}/approve` | `ApproverUser` + step role + anti-self | — | — | Y* | Y* | — | Y* | — |
| POST | `/approvals/{request_id}/reject` | `ApproverUser` + step role + anti-self | — | — | Y* | Y* | — | Y* | — |
| POST | `/approvals/{request_id}/request-revision` | `ApproverUser` + step role + anti-self | — | — | Y* | Y* | — | Y* | — |

`Y*` = permitted only when (a) the current pending step's `required_role`
matches the actor's role, or the actor is `ADMIN`; **and** (b) the actor did not
author or submit the quote.

### Portal (customer-only)

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/portal/quotes` | `CustomerUser` | — | — | — | — | — | — | Y |
| GET | `/portal/quotes/{quote_id}` | `CustomerUser` | — | — | — | — | — | — | Y |
| GET | `/portal/quotes/{quote_id}/messages` | `CustomerUser` | — | — | — | — | — | — | Y |
| POST | `/portal/quotes/{quote_id}/messages` | `CustomerUser` | — | — | — | — | — | — | Y |
| POST | `/portal/quotes/{quote_id}/confirm` | `CustomerUser` | — | — | — | — | — | — | Y |
| GET | `/quotes/{quote_id}/negotiation` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/quotes/{quote_id}/negotiation/reply` | `InternalUser` | — | Y | Y | Y | Y | Y | — |

### Orders and fulfillment

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/orders` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/orders/{order_id}` | `CurrentUser` + explicit customer block | — | Y | Y | Y | Y | Y | — |
| POST | `/orders/{order_id}/allocate` | `InternalUser` + inline `OPS`/`ADMIN`/`SALES` | — | Y | — | — | Y | Y | — |
| POST | `/orders/{order_id}/fulfill` | `InternalUser` + inline `OPS`/`ADMIN` | — | — | — | — | Y | Y | — |
| GET | `/orders/{order_id}/allocations` | `InternalUser` | — | Y | Y | Y | Y | Y | — |

### Billing

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/billing/schedules` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/billing/orders/{order_id}/summary` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/billing/proration-preview` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/billing/invoices` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/billing/invoices` | `InternalUser` + inline `FINANCE`/`ADMIN` | — | — | — | Y | — | Y | — |
| POST | `/billing/invoices/{invoice_id}/payments` | `InternalUser` + inline `FINANCE`/`ADMIN` | — | — | — | Y | — | Y | — |

### Dashboard and audit

| Method | Path | Guard | Guest | SALES | MANAGER | FINANCE | OPS | ADMIN | CUSTOMER |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/dashboard/control-tower` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/dashboard/attention-items` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| POST | `/dashboard/attention-items/{id}/resolve` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/dashboard/deal-health` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/dashboard/deal-health/{deal_id}` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/audit/events` | `InternalUser` | — | Y | Y | Y | Y | Y | — |
| GET | `/audit/quotes/{quote_id}/timeline` | `InternalUser` | — | Y | Y | Y | Y | Y | — |

---

## 4. Data-visibility matrix

What each role can see for the **same** quote version.

| Field group | SALES / MANAGER / FINANCE / OPS / ADMIN | CUSTOMER |
|---|---|---|
| Quote number, title, status | Y | Y |
| Line description, category, quantity | Y | Y |
| `unit_list_price`, `discount_pct`, `unit_net_price` | Y | Y |
| `gross_amount`, `discount_amount`, `net_amount`, `tax_amount`, `total_amount` | Y | Y |
| `payment_terms`, `valid_until`, `currency` | Y | Y |
| Billing type, recurring interval, periods | Y | Y |
| `unit_cost`, `line_cost` | Y | **Absent from schema** |
| `line_margin`, `line_margin_pct` | Y | **Absent from schema** |
| `total_cost`, `margin`, `margin_pct` | Y | **Absent from schema** |
| `blended_risk_score`, `risk_band` | Y | **Absent from schema** |
| `requires_approval`, `is_stale`, `stale_reason` | Y | **Absent from schema** |
| Policy results and violation reasons | Y | **No endpoint** |
| Approval steps, decisions, approver identities | Y | **No endpoint** |
| `DRAFT` versions | Y | **Filtered out** (`CUSTOMER_HIDDEN_VERSION_STATUSES`) |
| Blocked reason | Full internal reason | Safe paraphrase only: *"Your requested changes are being reviewed by our team"* |
| Audit trail | Y | **No endpoint** |
| Other customers' quotes | 404 | 404 |

---

## 5. Live verification

Executed against `http://127.0.0.1:8000` with seeded demo users. Actual response
bodies:

**No token → 401**
```json
{"error":{"code":"AUTHENTICATION_FAILED","message":"Missing bearer token.","details":{}}}
```

**Malformed token → 401**
```json
{"error":{"code":"AUTHENTICATION_FAILED","message":"Token is invalid or expired.","details":{}}}
```

**Access token sent to `/auth/refresh` → 401**
```json
{"error":{"code":"WRONG_TOKEN_TYPE","message":"Expected a refresh token, got 'access'.","details":{}}}
```

**`SALES` → `GET /users` → 403**
```json
{"error":{"code":"FORBIDDEN","message":"Role SALES cannot perform this action.","details":{"your_role":"SALES","allowed_roles":["ADMIN"]}}}
```

**`SALES` → `GET /approvals/inbox` → 403**
```json
{"error":{"code":"FORBIDDEN","message":"Role SALES cannot perform this action.","details":{"your_role":"SALES","allowed_roles":["ADMIN","FINANCE","MANAGER"]}}}
```

**`SALES` → `GET /portal/quotes` → 403**
```json
{"error":{"code":"INTERNAL_USER_FORBIDDEN","message":"Only customer portal users may use the portal endpoints.","details":{"your_role":"SALES"}}}
```

**`CUSTOMER` → `GET /deals` → 403**
```json
{"error":{"code":"PORTAL_USER_FORBIDDEN","message":"Customer portal users cannot access internal endpoints.","details":{"your_role":"CUSTOMER","use_instead":"/portal/*"}}}
```

**Unknown id → 404 (not 403), preventing enumeration**
```json
{"error":{"code":"NOT_FOUND","message":"Deal not found.","details":{}}}
```

The `allowed_roles` and `use_instead` hints in `details` are directly usable by
the frontend to render an accurate permission-denied screen instead of a generic
error.

---

## 6. Gaps in the permission layer

| # | Issue | Severity | Detail |
|---|---|---|---|
| 1 | `OpsUser` defined but unused | Low | [`app/dependencies.py`](../app/dependencies.py) line 123. Inline checks in the handler bodies do the work instead, so OPS/FINANCE restrictions are absent from the OpenAPI schema and generated clients |
| 2 | `POST /orders/{id}/allocate` permits `SALES` | Low | Broader than `OpsUser` would allow. Defensible (a rep may want to reserve stock) but undocumented |
| 3 | `ADMIN` bypasses per-step approver role | Medium | Break-glass by design and fully audited, but a production deployment wants a separate narrowly-scoped role. See [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) |
| 4 | `POST /dashboard/attention-items/{id}/resolve` open to all internal roles | Low | Any employee can resolve a `CRITICAL` stale-approval alert owned by `FINANCE`. Ownership is recorded but not enforced |
| 5 | No per-record ownership check on deals | Low | Any internal user in the organization can read and (if `SalesUser`) modify any deal, not only ones they own. Correct for a small sales team; would need territory scoping at scale |
| 6 | `TenantIsolationError` never raised | Informational | Defined in [`app/errors.py`](../app/errors.py) but cross-tenant access correctly returns 404 instead, which is the safer choice. Dead code |
