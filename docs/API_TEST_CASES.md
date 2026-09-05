# API TEST CASES

Integration scenarios for every major workflow. Each case gives the request,
the expected response, the expected database change, and the unauthorized and
invalid-input variants.

These mirror the automated suite — **433 tests, all passing** — so a case
marked *(automated)* names the test that already asserts it. Run:

```bash
ENVIRONMENT=test pytest                                       # all 433, ~6.6 min
ENVIRONMENT=test pytest tests/test_end_to_end.py -s           # narrated canonical flow
ENVIRONMENT=test pytest -m concurrency                        # row-locking only
python -m scripts.verify_db                                   # schema invariants
```

Fixture data throughout is the deterministic seed (§13 of
[`FRONTEND_INTEGRATION_GUIDE.md`](./FRONTEND_INTEGRATION_GUIDE.md)).

---

## How to read a case

| Field | Meaning |
|---|---|
| **Request** | Method, path, headers, body |
| **Expect** | Status and the assertions that matter |
| **DB** | Rows created, changed or deliberately unchanged |
| **Unauthorized** | What each disallowed role receives |
| **Invalid** | Validation and business-rule failures |

---

## 1. Authentication

### TC-1.1 Login succeeds *(automated: `test_auth.py::test_login_succeeds_and_records_last_login`)*

**Request**
```http
POST /auth/login
Content-Type: application/json

{"email": "sales@techsupply.com", "password": "Password123!"}
```

**Expect 200** — `tokens.access_token` and `refresh_token` are non-empty JWTs;
`tokens.expires_in == 3600`; `tokens.token_type == "bearer"`;
`user.role == "SALES"`; `user.is_internal == true`;
`user.organization_name == "TechSupply Solutions"`.

**DB** — `users.last_login_at` updated. One `audit_events` row,
`event_type = "USER_LOGGED_IN"`, `actor_email = "sales@techsupply.com"`,
`payload.role = "SALES"`, `ip_address` populated.

**Invalid**

| Input | Expect |
|---|---|
| Wrong password | 401 `AUTHENTICATION_FAILED` — *"Invalid email or password."* |
| Unknown email | 401 with the **same** message — existence is not disclosed |
| `{"email": "not-an-email"}` | 422 `VALIDATION_ERROR`; `details.errors` has entries for `["body","email"]` and `["body","password"]` |
| Deactivated user | 401 `USER_DISABLED` |
| Deactivated organization | 401 `ORGANIZATION_DISABLED` |

### TC-1.2 Login is rate limited *(automated: `test_security_hardening.py::test_repeated_failed_logins_are_rate_limited`)*

**Request** — 13 consecutive wrong-password attempts for the same email.

**Expect** — the first 10 return 401; the 11th onward return **429**
`RATE_LIMITED` with `details.limit == 10`, `details.retry_after_seconds > 0`
and a `Retry-After` header.

**DB** — no rows written by the refused attempts.

**Recovery** *(automated)* — a successful login clears that identity's
history, so a subsequent failure is a 401 again rather than a 429.

### TC-1.3 Token types are not interchangeable *(automated: `test_auth.py`)*

| Request | Expect |
|---|---|
| `POST /auth/refresh` with an **access** token | 401 `WRONG_TOKEN_TYPE` — *"Expected a refresh token, got 'access'."* |
| `Authorization: Bearer <refresh token>` on `/users/me` | 401 `WRONG_TOKEN_TYPE` |
| No `Authorization` header | 401 `AUTHENTICATION_FAILED` — *"Missing bearer token."* |
| Garbage token | 401 `AUTHENTICATION_FAILED` — *"Token is invalid or expired."* |

### TC-1.4 Signup creates a user and organization *(automated)*

**Request**
```http
POST /auth/signup
{"email":"new@acme.test","password":"Password123!","full_name":"New User",
 "role":"SALES","organization_name":"New Co"}
```

**Expect 201** — same shape as login.
**DB** — one `organizations` row, one `users` row (bcrypt hash, never
plaintext), `roles` seeded if absent, `USER_SIGNED_UP` audit event.

**Invalid**

| Input | Expect |
|---|---|
| Duplicate email | 409 `EMAIL_ALREADY_REGISTERED`, `details.email` |
| Neither org field | 400 `ORGANIZATION_REQUIRED` |
| `role: "CUSTOMER"` with `organization_kind: "SELLER"` | 400 `ROLE_ORG_MISMATCH` |
| Password `"12345678"` (all digits) | 422 — must mix letters and a non-letter |
| Password `"abcdefgh"` (all letters) | 422 |
| Password 7 chars | 422 |
| Unknown `organization_id` | 404 `NOT_FOUND` |

---

## 2. Role-based access *(automated: `test_rbac.py`, 54 cases)*

### TC-2.1 The permission matrix holds

| Request | Role | Expect |
|---|---|---|
| `GET /users` | SALES | 403 `FORBIDDEN`, `details.allowed_roles == ["ADMIN"]` |
| `GET /approvals/inbox` | SALES | 403, `allowed_roles == ["ADMIN","FINANCE","MANAGER"]` |
| `POST /billing/invoices` | SALES, MANAGER, OPS | 403, `allowed_roles == ["ADMIN","FINANCE"]` |
| `POST /orders/{id}/fulfill` | SALES, MANAGER, FINANCE | 403, `allowed_roles == ["ADMIN","OPS"]` |
| `POST /orders/{id}/allocate` | MANAGER, FINANCE | 403, `allowed_roles == ["ADMIN","OPS","SALES"]` |
| `POST /deals` | FINANCE, OPS | 403, `allowed_roles == ["ADMIN","MANAGER","SALES"]` |
| `GET /admin/settings` | every non-ADMIN | 403, `allowed_roles == ["ADMIN"]` |

Every response carries `details.your_role`, so the UI can say exactly why.

### TC-2.2 The portal boundary is bidirectional *(automated)*

| Request | Role | Expect |
|---|---|---|
| `GET /portal/quotes` | any internal | 403 `INTERNAL_USER_FORBIDDEN` |
| `GET /deals` | CUSTOMER | 403 `PORTAL_USER_FORBIDDEN`, `details.use_instead == "/portal/*"` |
| `GET /products` | CUSTOMER | 403 `PORTAL_USER_FORBIDDEN` |
| `GET /quote-versions/{id}` | CUSTOMER | 403 — the internal view carries cost and margin |
| `GET /orders/{id}` | CUSTOMER | 403 `PORTAL_USER_FORBIDDEN` |

The second direction is what makes the redacted view a real boundary rather
than a relabelled screen.

### TC-2.3 Tenant isolation returns 404, not 403 *(automated: `test_tenant_isolation.py`, 20 cases)*

**Setup** — two seller organizations, each with its own catalog and deals.

| Request | Expect |
|---|---|
| Org B reads Org A's deal id | **404** `NOT_FOUND` |
| Org B reads Org A's quote version | 404 |
| Org B reads Org A's order | 404 |
| Org B lists `/products` | Only its own; `total` excludes Org A's |
| Org B lists `/policies` | `[]` — a new tenant inherits none |
| Org B lists `/quotes` | `total == 0` |
| Org B reads `/reports/sales-performance` | `totals.quote_count == 0` |
| Customer of Org A reads a quote issued to Org B | 404, `details.reason == "not issued to your organization"` |

**Why 404** — a 403 would confirm the id exists, letting an attacker enumerate
identifiers across tenants.

---

## 3. Quote construction

### TC-3.1 Build the canonical quote *(automated: `test_end_to_end.py`)*

**Request**
```http
POST /deals/{deal_id}/quotes
Authorization: Bearer <sales>

{"title":"Acme Q1 laptop refresh",
 "lines":[
   {"product_id":"<HW-LAPTOP-01>","quantity":"100","discount_pct":"18"},
   {"product_id":"<HW-MONITOR-27>","quantity":"100","discount_pct":"16"},
   {"product_id":"<SV-INSTALL-01>","quantity":"1","discount_pct":"18"},
   {"product_id":"<SB-SUPPORT-01>","quantity":"1","discount_pct":"0"}]}
```

**Expect 201** — `quote_number == "Q-00001"`, `status == "OPEN"`,
`current_version_number == 1`, `versions[0].status == "DRAFT"`.

**DB and computed figures** — these exact values, hand-derived in the README:

| Field | Value |
|---|---|
| `gross_revenue` | `160800.00` |
| `total_discount` | `28090.00` |
| `net_revenue` | `132710.00` |
| `total_cost` | `100200.00` |
| `margin` | `32510.00` |
| `margin_pct` | `24.4970` |
| `effective_discount_pct` | `17.4689` |
| `one_time_revenue` | `132410.00` |
| `recurring_revenue` | `300.00` |
| `blended_risk_score` | `32.4440` (MEDIUM) |

Also: 4 `quote_lines`, 1 `commercial_snapshots` with `is_current = true`,
`policy_results` rows, `QUOTE_CREATED` audit event.

Each line's `unit_cost` is copied from the catalog — `HW-LAPTOP-01` is
`800.0000` — and cannot be supplied by the client.

**Invalid**

| Input | Expect |
|---|---|
| `unit_cost` in a line | 422 — `extra="forbid"` rejects unknown fields |
| `quantity: "0"` or negative | 422 |
| `discount_pct: "150"` | 422 |
| Product from another org | 404 `NOT_FOUND`, `details.product_id` |
| Inactive product | 404 |
| `recurring_periods` on a one-time product | 400 `BUSINESS_RULE_VIOLATION` |
| `product_variant_id` from a different product | 400 `VARIANT_PRODUCT_MISMATCH` |

### TC-3.2 Order-level discount compounds *(automated: `test_order_discount.py`)*

**Setup** — one line, 10 × 1200 at 10%.

**Request** `PATCH /quote-versions/{id}/discount` → `{"order_discount_pct":"5"}`

**Expect 200**

| Field | Value | Why |
|---|---|---|
| `gross_revenue` | `12000.00` | 10 × 1200 |
| `lines[0].discount_amount` | `1200.00` | Line tier only |
| `lines[0].order_discount_amount` | `540.00` | 5% of 10,800 |
| `net_revenue` | `10260.00` | 10,800 − 540 |
| `total_discount` | `1740.00` | Both tiers |
| `effective_discount_pct` | `14.5000` | Compounded, **not** 15% |

**Invariant** — `Σ lines[].net_amount == net_revenue`, and
`Σ (discount_amount + order_discount_amount) == total_discount`.

**Invalid** — `-1` or `101` → 422. Non-`DRAFT` version → 409
`IMMUTABLE_VERSION`.

### TC-3.3 The order tier cannot bypass a line ceiling *(automated — the load-bearing case)*

This is the loophole PDF §10 warns about: keeping every line technically
compliant while discounting the order more than intended.

**Setup** — one hardware line at 12%. The seeded Gold hardware ceiling is 15%.

| Step | Request | Expect |
|---|---|---|
| 1 | `GET .../policy-results` | `requires_approval == false` — 12% is inside 15% |
| 2 | `PATCH .../discount` `{"order_discount_pct":"10"}` | 200 |
| 3 | `GET .../policy-results` | `requires_approval == true` |

At step 3 the violated result reads `actual_value == "20.8000"` against
`threshold_value == "15.0000"`, and `detail` carries
`line_discount_pct: "12.0000"`, `order_discount_pct: "10.0000"`,
`effective_discount_pct: "20.8000"`.

If this case ever passes at step 3 with `requires_approval == false`, the
governance model is broken.

### TC-3.4 Immutability *(automated: `test_quote_versioning.py`, 39 cases)*

All 21 state × operation combinations are covered. Representative:

| Version status | `PATCH .../lines/{id}` | Expect |
|---|---|---|
| `DRAFT` | Any field | 200, full recalculated version |
| `PENDING_APPROVAL` | Any | 409 `IMMUTABLE_VERSION` — *"awaiting approval. Create a revision…"* |
| `APPROVED` | Any | 409 — *"approved and immutable. Create a revision; the existing approval will be re-checked for staleness."* |
| `SENT` | Any | 409 |
| `NEGOTIATING` | Any | 409 |
| `CONFIRMED` | Any | 409 — *"Confirmed versions are immutable forever."* |
| `REJECTED` | Any | 409 |
| `SUPERSEDED` | Any | 409 |

Every 409 carries
`details = {quote_version_id, version_number, status, editable_statuses:["DRAFT"]}`.

Revision attempts on a terminal state → 409 `VERSION_TERMINAL`.

**DB on refusal** — nothing changes. Verify `quote_lines.discount_pct` is
untouched.

### TC-3.5 What-if simulation persists nothing *(automated: `test_simulation.py`)*

**Request**
```http
POST /quote-versions/{id}/simulate
{"line_discounts": {"<line_id>": "30"}}
```

**Expect 200** — `persisted == false`; `baseline` and `proposed` both scored;
`margin_delta < 0`; `risk_delta > 0`; `approvals_added` contains
`"SALES_MANAGER"`; `verdict` is a complete sentence.

**DB — the critical assertion** — nothing at all. `quote_versions` count
unchanged, the version's own `net_revenue` / `margin` / `blended_risk_score`
byte-identical before and after, no new `policy_results`, no
`commercial_snapshots`, no audit event.

**Fidelity assertion** *(automated)* — simulate 22%, then actually apply 22%
and recalculate. `net_revenue`, `margin`, `margin_pct`, `blended_risk_score`
and `risk_band` must match **exactly**. A parallel implementation would drift;
this proves the same pure functions are used.

**Invalid**

| Input | Expect |
|---|---|
| Empty body | 422 — at least one hypothesis required |
| Line id from another quote | 404 `NOT_FOUND` |
| `line_discounts` value `150` | 422 |
| `line_quantities` value `0` | 422 |
| CUSTOMER role | 403 `PORTAL_USER_FORBIDDEN` |

---

## 4. Policy evaluation *(automated: `test_policy_engine.py`, 33 cases)*

### TC-4.1 Per-line ceilings resolve independently

The canonical quote breaches three ceilings at once, each judged against its
own category limit:

| Line | Given | Ceiling | Status | Overage |
|---|---|---|---|---|
| Business Laptop (HARDWARE) | 18% | 15% | `VIOLATED` | 3.0 |
| 27" Monitor (HARDWARE) | 16% | 15% | `VIOLATED` | 1.0 |
| Installation Service (SERVICE) | 18% | 10% | `VIOLATED` | 8.0 |
| Annual Support (SUBSCRIPTION) | 0% | 10% | `PASSED` | — |

Plus `DISCOUNT_AMOUNT_AUTHORITY`: 28,090 > 20,000 → `VIOLATED`, routes FINANCE.
And `MIN_MARGIN`: 24.4970% ≥ 10% → `PASSED`.

Every result has a non-empty `reason` naming the actual value, the threshold
and the overage.

### TC-4.2 Blended risk arithmetic *(automated: `test_blended_risk_matches_the_documented_formula`)*

| Component | Raw | Weight | Points | Cap |
|---|---|---|---|---|
| `WEIGHTED_DISCOUNT_OVERAGE` | 2.5023 | 3.0 | 7.5069 | 45 |
| `VIOLATION_BREADTH` | 3 lines | 5.0 | 15.0000 | 15 |
| `MARGIN_SHORTFALL` | 0 | 5.0 | 0.0000 | 40 |
| `DISCOUNT_DEPTH` | 17.4689 | 0.4 | 6.9876 | 15 |

Sum 29.4945 × 1.10 (GOLD) = **32.4440** → `MEDIUM`.

Each component returns its own `explanation`. `formula` and a prose
`explanation` accompany the score.

### TC-4.3 Routing is derived, not hardcoded

`required_approvals` == `[{type:"SALES_MANAGER"}, {type:"FINANCE"}]`, in
escalation order, each with `triggered_by[]` naming the reasons.

**Threshold is configurable** *(automated: `test_anomaly_and_signals.py`)* —
`PATCH /admin/settings {"finance_escalation_threshold":"10"}` then re-read
`policy-results`: FINANCE is now required on risk alone, and
`blended_risk.score` is **unchanged**. The threshold changes who signs, not
how risky the deal is.

### TC-4.4 A clean quote needs nobody *(automated)*

5 laptops at 10% (inside every ceiling, margin healthy):
`requires_approval == false`, `blended_risk_score == "0.0000"`, band `NONE`.

On submit the version goes `DRAFT` → **`APPROVED`** directly, and an
`approval_requests` row is still written with `status = "APPROVED"` and **zero
steps** — so a later material change has a decision to invalidate.

---

## 5. Approval workflow *(automated: `test_approval_flow.py`, 17 cases)*

### TC-5.1 Submit routes automatically

`POST /quote-versions/{id}/submit` `{}` → 200 `DecisionFabricResult`.

**DB** — version → `PENDING_APPROVAL`, `submitted_at` set; one
`approval_requests` (`PENDING`, `current_step_sequence = 1`); two
`approval_steps` (seq 1 `SALES_MANAGER`/`MANAGER`, seq 2 `FINANCE`/`FINANCE`,
both `PENDING`); a `PENDING_APPROVAL` attention item; `QUOTE_SUBMITTED`,
`POLICY_EVALUATED` and `APPROVAL_REQUESTED` audit events.

The rep never asked for approval — this is PDF QT3.

**Invalid** — non-`DRAFT` → 409 `VERSION_NOT_DRAFT`; zero lines → 400
`EMPTY_QUOTE`.

### TC-5.2 Steps are ordered

| Actor | Request | Expect |
|---|---|---|
| FINANCE (step 2) first | `POST /approvals/{id}/approve` | **403** `WRONG_APPROVER_ROLE`, `details.required_role == "MANAGER"`, `your_role == "FINANCE"`, `level == "SALES_MANAGER"` |
| MANAGER | approve | 200, `quote_version_status == "PENDING_APPROVAL"`, `message` names Finance next |
| FINANCE | approve | 200, `quote_version_status == "APPROVED"` |

**DB after both** — request `APPROVED`, both steps `APPROVED`, version
`APPROVED` with `approved_at` set and `is_stale = false`, two
`approval_decisions` each with actor id, role, email, reason and a
`decision_snapshot` where `margin_pct == "24.4970"`.

### TC-5.3 Self-approval is impossible *(automated)*

A MANAGER who authored the quote calling approve → **403**
`SELF_APPROVAL_FORBIDDEN` with `actor_user_id`, `requested_by_user_id` and
`version_created_by_user_id` in `details`.

Applies to `ADMIN` too: authorship disqualifies an approver, not role.

### TC-5.4 A decided step cannot be re-decided

Second approve on the same step → 409 `NO_PENDING_STEP` with
`details.already_decided[]`. Deciding an `APPROVED` request → 409
`APPROVAL_NOT_PENDING` with `details.status`.

Two approvers clicking simultaneously: one wins, the other gets 409 — the UI
should refetch, not report a failure.

### TC-5.5 Reject and return

| Decision | Version becomes | Other pending steps |
|---|---|---|
| `reject` | `REJECTED` (immutable forever) | `SKIPPED` |
| `request-revision` | `DRAFT` (editable again), `submitted_at` cleared | `SKIPPED` |

Both require a non-empty `reason` → 422 otherwise. Both write an
`approval_decisions` row and an audit event.

---

## 6. Portal negotiation and staleness *(automated: `test_negotiation.py`, `test_decision_fabric.py`)*

### TC-6.1 The portal leaks nothing *(automated — asserted on the serialised payload)*

`GET /portal/quotes/{id}` as CUSTOMER → 200.

**Assert the response body contains none of** the substrings `unit_cost`,
`line_cost`, `line_margin`, `internal_cost`, `margin`, `risk`, **nor the
literal internal values** `100200`, `32510`, `24.4970`, `800.0000`.

It does contain `total_revenue == "132710.00"`,
`seller_name == "TechSupply Solutions"`, per-line discounts and net prices.

`DRAFT` versions are filtered out entirely.

### TC-6.2 Counter-offer → staleness → block → recovery

The single most important scenario in the system.

| Step | Actor | Request | Expect |
|---|---|---|---|
| 1 | CUSTOMER | `POST /portal/quotes/{id}/messages` with `COUNTER_OFFER`, laptop line at 25% | 201; `new_version_number == 2`; `requires_reapproval == true`; `customer_message` contains *"reviewing the updated terms"* |
| 2 | SALES | `GET /quote-versions/{v1}` | `status == "SUPERSEDED"`, `net_revenue` still exactly `132710.00` — **v1 was never mutated** |
| 3 | SALES | `GET /quote-versions/{v2}` | `net_revenue == "124310.00"`, `margin == "24110.00"`, `margin_pct == "19.3951"`, `is_stale == true` |
| 4 | SALES | `GET /quote-versions/{v2}/impact` | `has_material_change == true`; `blocks_confirmation == true`; `material_changes` fields include `discount_pct` and `margin_pct`; `stale_decisions[0].previous_decision == "APPROVED"` |
| 5 | CUSTOMER | `POST /portal/quotes/{id}/confirm` | **409 `STALE_APPROVAL`** |
| 6 | CUSTOMER | `GET /portal/quotes/{id}` | `can_confirm == false`; `blocked_reason` contains *"being reviewed by our team"* and **does not** contain the word "margin" |
| 7 | MANAGER, FINANCE | approve v2 | `is_reapproval == true` in the inbox |
| 8 | SALES | `GET /quote-versions/{v2}` | `is_stale == false` |
| 9 | CUSTOMER | confirm | 200, order created |

**DB after step 1, in one transaction** — v1 `SUPERSEDED`; v2 created with
`source = "CUSTOMER_COUNTER"` and `parent_version_id = v1`; lines cloned with
`source_line_id` provenance; v1's approval request → `STALE` with `stale_at`
and `stale_reason` (**retained, never deleted**); a new `PENDING` request with
`superseded_by_request_id` linked; `decision_impacts` rows for every diff
including non-material ones; a `CRITICAL` `STALE_APPROVAL` attention item
owned by FINANCE; `CUSTOMER_COUNTERED`, `QUOTE_REVISED`,
`MATERIAL_CHANGE_DETECTED` and `APPROVAL_MARKED_STALE` audit events.

**Invalid**

| Input | Expect |
|---|---|
| `COUNTER_OFFER` with no `lines` | 422 |
| `lines` on a plain `COMMENT` | 422 |
| `message_type: "SELLER_REPLY"` from a customer | 422 |
| Line id not on the current version | 404 |
| Counter with no actual change | 400 `EMPTY_COUNTER_OFFER` |
| Counter on a `CONFIRMED` quote | 409 `ALREADY_CONFIRMED` |

### TC-6.3 Materiality is fail-closed *(automated)*

| Change | Material? |
|---|---|
| `discount_pct` 18 → 18.005 | No — below the 0.01pp epsilon |
| `discount_pct` 18 → 19 | Yes |
| `quantity` any change | Yes |
| Line added or removed | Yes |
| `payment_terms` change | Yes |
| `description` or `notes` only | **No** — recorded in `decision_impacts` with `material = false`, never triggers staleness |

Non-material diffs are still persisted, so the impact endpoint can state
*"we looked at this and it did not matter."*

---

## 7. Order confirmation and idempotency *(automated: `test_idempotency.py`)*

### TC-7.1 Confirmation creates exactly one order

**Request**
```http
POST /portal/quotes/{quote_id}/confirm
Authorization: Bearer <customer>
Idempotency-Key: 3f2b8c1e-...

{"acceptance_note": "Approved by our procurement board."}
```

**Expect 200** — `order.order_number == "SO-00001"`,
`order.total_amount == "124310.00"`, `idempotent_replay == false`. The
response contains **no** `margin` or cost field.

**DB, atomically** — version → `CONFIRMED`; quote → `CONFIRMED`; deal →
`CLOSED_WON`; negotiation thread → `RESOLVED`; one `sales_orders` (4 lines);
4 `billing_schedules`; `idempotency_keys` row `COMPLETED` with the response
cached; `QUOTE_CONFIRMED`, `ORDER_CREATED`, `BILLING_SCHEDULED` audit events.

### TC-7.2 Replay is safe *(automated)*

Repeat TC-7.1 with the **same key and body** → 200, `idempotent_replay: true`,
same `order.id`, message *"This quote was already confirmed; returning the
existing order."*

**DB** — `sales_orders` count still exactly 1.

| Variant | Expect |
|---|---|
| Same key, **different** body | 409 `IDEMPOTENCY_KEY_REUSED` |
| Same key while still processing | 409 `IDEMPOTENT_REQUEST_IN_FLIGHT` |
| **No** key, confirmed twice | Second returns the existing order — `UNIQUE (sales_orders.quote_version_id)` makes a duplicate impossible |

### TC-7.3 The confirmation gate

| Version state | Expect |
|---|---|
| `DRAFT` | 400 `VERSION_NOT_SENT` |
| `PENDING_APPROVAL` | 409 `APPROVAL_REQUIRED`, `details.awaiting[]` |
| Approved but `is_stale` | 409 `STALE_APPROVAL` |
| Latest request `STALE` | 409 `STALE_APPROVAL` |
| `REJECTED` / `SUPERSEDED` | 409 `VERSION_NOT_CONFIRMABLE` |
| Already `CONFIRMED` | 409 `ALREADY_CONFIRMED` |
| `APPROVED` / `SENT` / `NEGOTIATING`, not stale | 200 |

---

## 8. Inventory allocation *(automated: `test_inventory.py`, 20 cases incl. concurrency)*

### TC-8.1 The 60/40 split is emergent

**Setup** — Main has 60 laptops (priority 10, ship 120), East has 40
(priority 20, ship 180). Order needs 100.

**Request** `POST /orders/{id}/allocate` `{}` as OPS.

**Expect 200** — `fully_allocated == true`, `has_backorder == false`,
`shipment_count == 2`, `estimated_shipping_cost == "300.00"`; the laptop
line's `splits` are `{MAIN: 60, EAST: 40}`; `explanation` reads *"Sourced 60
from Main Warehouse, 40 from East Depot; across 2 shipments because no single
warehouse held all 100 units."*

**DB** — `inventory_allocations` rows per split; `inventory.quantity_reserved`
incremented; `quantity_available` now exactly `0` at both warehouses;
`sales_order_lines.quantity_allocated == 100`; order → `ALLOCATED`;
`INVENTORY_ALLOCATED` audit event.

### TC-8.2 Nothing about the split is hardcoded *(automated: `test_split_changes_when_stock_changes`)*

Rebalance the seed to Main 30 / East 70 and re-run: the split becomes 30/70.
The algorithm is generic; 60/40 is a property of the data.

**This is the test to run when a judge asks whether the demo is scripted.**

### TC-8.3 Backorder and consolidation

**Setup** — only 40 units available, order needs 100.

**Expect** — `has_backorder == true`; one allocation `BACKORDERED` with
`warehouse_id == null` (enforced by a CHECK constraint) and
`expected_available_at` populated; order → `PARTIALLY_ALLOCATED`; an
`INVENTORY_SHORTAGE` attention item owned by OPS.

**Then** `POST /admin/inventory/adjust` with a positive delta → the backorder
is consolidated automatically into a real reservation (PDF B6).

### TC-8.4 Over-allocation is impossible *(automated, `-m concurrency`)*

Two concurrent allocations for the last unit: `SELECT ... FOR UPDATE` over
every stock row for the product, locked in `inventory.id` order with lines
processed in `product_id` order, serialises them. One succeeds; the other
backorders or fails. `quantity_reserved` never exceeds `quantity_on_hand` —
and a CHECK constraint is the backstop even if the service were wrong.

**Invalid**

| Input | Expect |
|---|---|
| `allow_partial: false` with a short line | 409 `INSUFFICIENT_INVENTORY`, **nothing reserved** |
| Override exceeding real availability | 409 `INSUFFICIENT_INVENTORY` naming warehouse and numbers |
| Override exceeding the line's outstanding quantity | 400 `OVERRIDE_EXCEEDS_LINE` |
| Override for a line not on the order | 404 |
| Cancelled order | 409 `ORDER_CANCELLED` |

### TC-8.5 Fulfil, deliver, cancel

| Request | Expect | DB |
|---|---|---|
| `POST /orders/{id}/fulfill` `{"carrier":"DHL","tracking_number":"TRK-1"}` | 200, 2 `fulfillments` | Allocations → `SHIPPED`; **both** `quantity_on_hand` and `quantity_reserved` decremented; order → `FULFILLED` |
| Fulfil with nothing allocated | 409 `NOTHING_TO_FULFILL` | — |
| `POST /orders/{id}/fulfillments/{fid}/deliver` | 200 | Fulfilment → `DELIVERED`, `delivered_at` set; `ORDER_DELIVERED` event |
| Deliver twice | 409 `ALREADY_DELIVERED` | — |
| `POST /orders/{id}/cancel` `{"reason":…}` *(automated)* | 200 | Reservations → `RELEASED`, **stock returns to available**; uninvoiced schedules → `CANCELLED`; order → `CANCELLED` |
| Cancel after shipping | 409 `ORDER_ALREADY_SHIPPED` | — |

TC-8.5's cancel case matters: without releasing reservations, an abandoned
order would lock stock out of every future sale while appearing available
nowhere.

---

## 9. Billing and subscriptions *(automated: `test_billing.py` 23, `test_subscription_lifecycle.py` 14)*

### TC-9.1 One order carries both billing kinds *(PDF QT6)*

`GET /billing/schedules?sales_order_id={id}` → 3 `ONE_TIME` + 1 `RECURRING`.

For the v1-confirmed order: one-time schedules sum to `132410.00`, the
recurring schedule is `300.00` `YEARLY`. (After a 25% counter-offer the
one-time total is `124010.00` — the README's figure.)

**Invariant** — `SUM(schedule.amount) == line.net_amount` **exactly** for any
period count; the final period absorbs the remainder. Verified for awkward
shapes like 0.05 over 4 periods.

Due date = `period_start + TERMS_DAYS[payment_terms]`. Recurring periods are
contiguous and month-end clamped (31 Jan + 1 month = 28 Feb, 29 in a leap
year).

### TC-9.2 Payment updates invoice status *(PDF QT8)*

| Step | Request | Expect |
|---|---|---|
| 1 | `POST /billing/invoices` `{billing_schedule_id}` as FINANCE | 201, `status == "ISSUED"`; schedule → `INVOICED` |
| 2 | `POST /billing/invoices/{id}/payments` `{amount: partial}` | 201; invoice → `PARTIALLY_PAID` |
| 3 | Pay the remainder | invoice → `PAID`, `paid_at` set, linked schedule → `COMPLETED` |

**Invalid** — over-payment → 400 `OVERPAYMENT` with `details.amount_due`;
re-invoicing → 409 `SCHEDULE_ALREADY_INVOICED`; paying a void invoice → 409
`INVOICE_VOID`; non-Finance → 403.

`is_overdue` / `days_overdue` are computed on read — a freshly issued NET 30
invoice reports `false` / `0`.

### TC-9.3 Mid-cycle quantity change prorates *(automated)*

**Request**
```http
POST /billing/subscriptions/{schedule_id}/change
{"new_quantity":"3","effective_date":"<period_start + 180d>",
 "reason":"Customer added two more seats."}
```

**Expect 200** — `change_type == "QUANTITY"`;
`previous_period_amount == "300.00"`; `new_period_amount == "900.00"`;
`proration_charge > 0`; `proration_credit == "0"`; `credit_note_id == null`;
`explanation` states the arithmetic and the effective date.

**DB** — the current period rewritten to a blended amount (consumed at the old
rate + remainder at the new), `is_prorated = true`, status → `ACTIVE`,
`detail` recording both quantities and the proration explanation; later
uninvoiced periods regenerated at the new rate; `sales_order_lines.quantity`
updated; `SUBSCRIPTION_CHANGED` audit event.

**Invalid**

| Input | Expect |
|---|---|
| One-time schedule | 400 `SUBSCRIPTION_NOT_RECURRING` |
| Already invoiced period | 409 `PERIOD_ALREADY_INVOICED` — invoiced documents are immutable |
| `effective_date` outside the period | 400 `EFFECTIVE_DATE_OUTSIDE_PERIOD` |
| Empty body | 422 |
| SALES / MANAGER / OPS | 403, `allowed_roles == ["ADMIN","FINANCE"]` |

### TC-9.4 Cancellation credits the unused portion *(automated)*

**Setup** — invoice the recurring period first, then cancel at day 180.

**Expect 200** — `change_type == "CANCELLATION"`;
`new_period_amount < 300.00` (consumed only); `proration_credit > 0`;
`credit_note_id` present; `explanation` mentions the credit note.

**DB** — schedule → `CANCELLED` with the arithmetic in `detail`; later periods
`CANCELLED`; one `credit_notes` row `ISSUED`, reason
`SUBSCRIPTION_CANCELLED`, `total_amount == proration_credit`, `detail`
retaining the proration explanation; `SUBSCRIPTION_CANCELLED` and
`CREDIT_NOTE_ISSUED` audit events.

### TC-9.5 Refund reaches `PaymentStatus.REFUNDED` *(automated)*

Pay the invoice in full, cancel mid-period, then
`POST /billing/credit-notes/{id}/refund` `{}` → 200,
`status == "APPLIED"`, `amount_outstanding == "0.00"`.

**DB** — a `payments` row with `status = "REFUNDED"` referencing the credit
note; `invoices.amount_paid` reduced and status recomputed;
`CREDIT_NOTE_REFUNDED` audit event.

**Invalid** — refund above the balance → 400 `REFUND_EXCEEDS_CREDIT`;
zero/negative → 400 `INVALID_REFUND_AMOUNT`; voiding a partly-refunded note →
409 `CREDIT_NOTE_PARTLY_REFUNDED`.

---

## 10. Dashboard and B9 signals *(automated: `test_dashboard.py` 21, `test_anomaly_and_signals.py` 13)*

### TC-10.1 Attention items are raised at decision points only *(automated)*

Recalculating a draft three times → `/dashboard/attention-items` returns `[]`.
A draft being priced is not asking anyone for a decision; raising items on
every keystroke would make the queue unreadable.

Submitting → one `PENDING_APPROVAL` item owned by MANAGER, with non-empty
`reason`, `impact` and `recommended_action`.

**Dedupe** *(automated)* — repeated upserts refresh one row rather than adding,
enforced by a partial unique index on `(org, source_type, source_id, type)
WHERE status <> 'RESOLVED'`.

### TC-10.2 Item ownership is enforced *(automated)*

| Actor | Request | Expect |
|---|---|---|
| SALES (not the owner) | `POST .../{id}/resolve` on a MANAGER-owned item | **403** `NOT_ITEM_OWNER`, `details.owner_role == "MANAGER"` |
| MANAGER (the owner) | resolve | 200, `status == "RESOLVED"`, `resolved_at` set |
| ADMIN | resolve | 200 — break-glass retained |

Without this, the rep whose quote triggered a governance alert could clear it
from the manager's queue.

### TC-10.3 Nudge, acknowledge, escalate *(automated)*

| Request | Expect |
|---|---|
| `POST .../{id}/nudge` as **any** internal role | 200; `nudge_count == 1`; `notified_role == "MANAGER"`; display-ready `message` |
| `POST .../{id}/acknowledge` as owner | 200; `status == "ACKNOWLEDGED"`; `acknowledged_at` set |
| `POST .../{id}/escalate` `{"note":…,"owner_role":"FINANCE"}` | 200; severity raised one band; `owner_role == "FINANCE"`; `escalated_at` and `escalation_note` set |
| Any of the three on a `RESOLVED` item | 409 `ITEM_ALREADY_RESOLVED` |

Nudge is open to all internal roles deliberately — the point is to prod the
owner, so restricting it to the owner would make it useless.

### TC-10.4 Discount anomaly vs the rep's own history *(automated)*

**Setup** — `PATCH /admin/settings {"discount_anomaly_min_samples":2,
"discount_anomaly_sigma":"1.0"}`, then submit quotes at 4%, 5%, 4%, 6%, then
one at **14%**.

**Expect** — a `DISCOUNT_ANOMALY` attention item owned by MANAGER, whose
`reason` contains *"standard deviations above"* and *"average of"*, with
`detail.baseline.sample_count >= 2` and `detail.is_anomaly == true`.

**The point** — that same 14% quote has `requires_approval == false`, because
14% is inside the 15% Gold ceiling. The anomaly is a **behavioural** signal
that fires on a fully policy-compliant quote. A ceiling check is structurally
blind to it.

**Suppression** *(automated)* — below `min_samples`, no item is raised, and
`reason` explains why: *"…has 1 prior quote(s), and 5 are required before a
personal baseline is statistically meaningful."* A new rep is not flagged on
their first discount.

### TC-10.5 Delivery promise slippage *(automated)*

| Step | Request | Expect |
|---|---|---|
| 1 | `PATCH /orders/{id}/promise` with today + 7 | `is_delivery_late == false`, `days_late == 0` |
| 2 | `PATCH .../promise` with today − 3 | `is_delivery_late == true`, `days_late == 3` |
| 3 | `GET /orders?overdue_delivery=true` | `total == 1`, `items[0].days_late == 3` |

Dates are UTC — the server computes in UTC, so a test or client east of
Greenwich must anchor on UTC, not local midnight.

### TC-10.6 Deal health explains every deduction *(automated)*

`GET /dashboard/deal-health` → `average_health`, and per deal a
`health_score` 0–100, a `health_band`, and `signals[]` where **every entry
carries its own `points`**:

| Signal | Points |
|---|---|
| `STALE_APPROVAL` | −25 (and `blocked = true`) |
| `LOW_MARGIN` | −20 |
| `DELIVERY_SLIPPAGE` | −15 |
| `PENDING_APPROVAL` | −10 (and `blocked = true`) |
| `NO_CUSTOMER_RESPONSE` | −10, after the configured window |
| `DISCOUNT_ANOMALY` | −10 |
| `INVENTORY_SHORTAGE` | −10 |
| `NO_QUOTE` | −10 |
| `HEALTHY` | 0 |

`CLOSED_WON` → 100, `CLOSED_LOST` → 0. Bands: ≥80 HEALTHY, ≥60 WATCH,
≥40 AT_RISK, else CRITICAL.

The stalled window comes from `organization_settings.stalled_deal_days`, not a
compiled-in constant *(automated)*.

---

## 11. Reporting and export *(automated: `test_reporting.py`, 18 cases)*

### TC-11.1 Sales performance arithmetic

`GET /reports/sales-performance?group_by=rep` after the canonical quote →
one row, `group_label == "Sam Rivera"`, `quote_count == 1`,
`gross_revenue == "160800.00"`, `net_revenue == "132710.00"`,
`margin == "32510.00"`, `margin_pct == "24.4970"`, and
`totals.effective_discount_pct == "17.4689"`.

Measured over **quote versions**, so a discounted deal that was lost still
counts — restricting to orders would hide the losses.

**Group-by allowlist** — `rep` `customer` `tier` `stage` `status` `month`
`risk_band` all return 200; anything else → 422 `INVALID_GROUP_BY`.

### TC-11.2 All four PDF A7 filters work

| Filter | Case | Expect |
|---|---|---|
| Period | `period=custom&date_from&date_to` | `filters.period == "2026-01-01 to 2026-12-31"` |
| Period | `period=custom` alone | 422 `PERIOD_RANGE_REQUIRED` |
| Period | `date_to < date_from` | 422 `INVALID_PERIOD_RANGE` |
| Rep | `rep_user_id=<sales>` | `totals.quote_count == 1` |
| Rep | `rep_user_id=<unrelated>` | `quote_count == 0` |
| Team | `team_id=<WEST>` | `quote_count == 1`; the seeded team includes `sales@techsupply.com` |
| Approval status | `approval_status=PENDING` | `by_status.PENDING.count == 1`, `total_value == "132710.00"` |
| Product / category | `product_id`, `category` | Narrows the aggregate |

`by_status` reports **every** state including zeros — an absent key would force
the client to guess.

### TC-11.3 Export produces real files

For each of the five reports × `csv` | `xlsx` | `pdf` → 200, non-empty body,
`Content-Disposition: attachment; filename="dealflow360-<report>-<ts>.<ext>"`.

**File signatures asserted** — `xlsx` starts with `PK` (a zip), `pdf` starts
with `%PDF`. Content types are `text/csv`,
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and
`application/pdf`.

**Invalid** — `format=docx` → 422. Missing optional dependency → 400
`EXPORT_DEPENDENCY_MISSING` with `details.package`.

`GET /reports/export/formats` advertises `{formats, default, reports}`.

---

## 12. Pagination and list contract *(automated: `test_pagination.py`, 9 cases)*

### TC-12.1 The Page envelope

Every one of `/quotes`, `/deals`, `/products`, `/orders`, `/audit/events`,
`/dashboard/attention-items` returns `{items, total, limit, offset}` with
`limit == 25` and `offset == 0` by default.

### TC-12.2 Paging is correct

`limit=2` → `total == 4`, 2 items. `limit=2&offset=2` → `total == 4`, 2
items, **no overlap** with the first page. `offset=10` → `items == []` and
`total == 4` (the unpaginated count).

### TC-12.3 Bounds and allowlists

| Input | Expect |
|---|---|
| `limit=0`, `-1`, `201`, `5000` | 422 |
| `offset=-1` | 422 |
| `sort_by=internal_cost); DROP` | 422 `INVALID_SORT_FIELD` with `details.allowed` |
| `sort_dir=asc` vs `desc` | Different ordering |
| `q=LAPTOP` | `total == 1`, the laptop SKU |
| `q=nothing-matches` | `total == 0`, `items == []` |

The sort allowlist matters: `sort_by` reaches an `ORDER BY` clause.

### TC-12.4 Quote list carries the card fields *(automated: `test_quote_list.py`)*

`GET /quotes` → `customer_display_name`, `customer_tier`, `deal_stage`,
`total_revenue`, `margin_pct`, `risk_band`, `owner_name`, `line_count`,
`version_count`, `age_days` — everything a PDF B2 card needs, in one request.

Filters verified: `version_status` (separates pipeline columns), `is_stale`
(surfaces blocked quotes, `version_count == 2` after a counter-offer), and `q`
matching number, title or customer name.

---

## 13. Security *(automated: `test_security_hardening.py`, 11 cases)*

### TC-13.1 Startup validators refuse the demo posture in production

| `Settings(...)` | Expect |
|---|---|
| `environment="production"` + placeholder `jwt_secret_key` | `ValueError` naming *placeholder* |
| `environment="production"` + `cors_origins="*"` | `ValueError` naming `CORS_ORIGINS` |
| `environment="production"` + `debug=True` | `ValueError` naming `DEBUG` |
| `environment="production"` + real secret, explicit origins, `debug=False` | **Accepted**; `docs_enabled == False` |
| `environment="development"` (defaults) | Accepted; `docs_enabled == True`; `cors_origin_list == ["*"]`; `effective_cors_allow_credentials == False` |

The last two matter equally: the validator must not be so strict that a real
deployment cannot boot, and development must keep the open docs and CORS that
make the system explorable.

### TC-13.2 CORS never pairs a wildcard with credentials

Preflight from `http://evil.example.com` → `access-control-allow-credentials`
is **not** `"true"`. Allowed methods exclude `TRACE`.

A wildcard origin collapses `allow_credentials` to false in config, because
Starlette otherwise echoes the requesting origin and defeats the browser's own
protection.

### TC-13.3 Injection and malformed input

| Input | Expect |
|---|---|
| `'; DROP TABLE users; --` in `q` | 200, zero matches — ORM parameter binding, no interpolation |
| Malformed UUID in a path | 422 `VALIDATION_ERROR`, `details.errors[0].type == "uuid_parsing"` |
| Unknown field in any request body | 422 — `extra="forbid"` |
| Unknown route | 404 `NOT_FOUND` in the standard envelope |
| Wrong method | 405 `METHOD_NOT_ALLOWED` in the standard envelope |
| Oversized string | 422 with the max length |

No error leaks a stack trace, SQL, or an internal identifier.

---

## 14. Data integrity *(automated: `test_models.py` 22, `scripts/verify_db.py`)*

### TC-14.1 Schema invariants

`python -m scripts.verify_db` asserts and currently reports:

```
[tables]   expected 38, found 38
[fks]      132 foreign keys across 36 tables
[constraints] 736 total; checking business invariants
  ✓ sales_orders.uq_sales_orders_quote_version_id — one order per quote version
  ✓ inventory.ck_inventory_no_over_reservation — inventory cannot over-reserve
  ✓ quote_versions.uq_quote_versions_quote_id_version_number
  ✓ quote_lines.ck_quote_lines_discount_pct_range — 0..100
  ✓ billing_schedules.ck_billing_schedules_recurring_requires_interval
  ✓ sales_order_lines.ck_..._quantity_allocated_within_bounds
[indexes]  235 total; checking partial unique indexes
  ✓ approval_requests.uq_approval_requests_one_pending_per_version
  ✓ attention_items.uq_attention_items_live_per_source
[money]    ✓ zero float/double columns — all money is NUMERIC (110 columns)
[time]     ✓ all timestamps are timezone-aware
VERIFICATION PASSED
```

### TC-14.2 Database-level refusals

| Attempt | Expect |
|---|---|
| Insert `quote_lines.discount_pct = 150` directly | `IntegrityError` (CHECK) |
| Set `inventory.quantity_reserved > quantity_on_hand` | `IntegrityError` |
| Two `sales_orders` for one `quote_version_id` | `IntegrityError` (UNIQUE) |
| Two `PENDING` approvals for one version | `IntegrityError` (partial UNIQUE) |
| `BACKORDERED` allocation with a `warehouse_id` | `IntegrityError` |
| `RECURRING` schedule without an interval | `IntegrityError` |
| Delete a product that has been sold | `IntegrityError` (FK RESTRICT) |

### TC-14.3 Audit trail *(automated: `test_audit.py`, 14 cases)*

The canonical flow produces **22 events in monotonic `sequence` order**,
including `QUOTE_CREATED`, `QUOTE_SUBMITTED`, `POLICY_EVALUATED`,
`APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `QUOTE_APPROVED`, `QUOTE_SENT`,
`CUSTOMER_COUNTERED`, `QUOTE_REVISED`, `MATERIAL_CHANGE_DETECTED`,
`APPROVAL_MARKED_STALE`, `QUOTE_CONFIRMED`, `ORDER_CREATED`,
`INVENTORY_ALLOCATED`, `BILLING_SCHEDULED`, `ORDER_FULFILLED`.

Assertions: every business event has a non-null `actor_email`;
`sequences == sorted(sequences)`; **every money value in every payload is a
string** (walked exhaustively — a float round-trip through JSONB would corrupt
the record of a decision); approval events embed
`financials_at_decision`; `audit_events` has no `updated_at` column, so there
is structurally nothing to rewrite history with.

---

## 15. Regression guards

Cases whose failure indicates a design regression rather than a bug.

| Guard | Asserts | Test |
|---|---|---|
| **Order discount cannot bypass a ceiling** | The PDF §10 loophole stays closed | `test_order_discount.py` |
| **Zero order discount is a no-op** | The canonical figures are unchanged by the new column | `test_order_discount.py` |
| **Simulation matches a real submit** | The what-if path uses the same pure functions, so it cannot drift | `test_simulation.py` |
| **Simulation persists nothing** | No version, snapshot, policy result or audit event | `test_simulation.py` |
| **Split follows the data** | Allocation is generic, not tuned to the demo | `test_inventory.py` |
| **Portal payload leaks nothing** | Redaction is structural | `test_end_to_end.py`, `test_negotiation.py` |
| **v1 is byte-identical after a counter** | Versions are immutable | `test_end_to_end.py` |
| **Exactly one order per version** | Idempotency plus the UNIQUE backstop | `test_idempotency.py` |
| **Schedules sum to the line exactly** | Rounding remainder is absorbed | `test_billing.py` |
| **Anomaly fires on a compliant quote** | Behavioural detection is independent of policy | `test_anomaly_and_signals.py` |
| **Invoiced periods are immutable** | Financial documents are not rewritten | `test_subscription_lifecycle.py` |
| **Cancelling releases stock** | No permanently-reserved inventory | `test_anomaly_and_signals.py` |
| **Non-owner cannot resolve an alert** | The Control Tower cannot be emptied by the subject of the alert | `test_dashboard.py` |
| **Zero float columns** | Money cannot drift | `test_models.py`, `verify_db.py` |
| **38 tables match the ORM** | Declared inventory and metadata cannot diverge | `test_models.py` |

---

## 16. The PDF Quick Test Flow, as executable cases

PDF §9 gives eight steps and states: *"If all eight steps work smoothly and
each result matches what is expected, the core flow is solid."* All eight pass.

| Step | Requirement | Case | Status |
|---|---|---|---|
| QT1 | Set up a discount tier, a warehouse, a subscription plan | `POST /admin/policies`, `/admin/warehouses`, `/admin/products` (RECURRING) — or `POST /admin/seed` | Pass |
| QT2 | Quote a line above the allowed discount | TC-3.1 — 18% against a 15% ceiling | Pass |
| QT3 | Approval is requested **automatically** | TC-5.1 — no manual request | Pass |
| QT4 | Accept an upsell; total and margin update at once | `GET /quotes/{id}/recommendations` → `POST .../lines` → `POST .../calculate` | Pass |
| QT5 | Stock pulled from the right warehouse, split across two | TC-8.1 — 60 Main + 40 East | Pass |
| QT6 | One-time and recurring billed separately on one order | TC-9.1 | Pass |
| QT7 | Customer requests a bigger discount → back for approval automatically | TC-6.2 | Pass |
| QT8 | Confirm, record a payment, invoice status updates | TC-7.1 + TC-9.2 | Pass |

---

## 17. Running the suite

```bash
docker compose up -d                        # PostgreSQL on 5433
ENVIRONMENT=test pytest                     # 433 tests, ~6.6 min
ENVIRONMENT=test pytest tests/test_end_to_end.py -s
ENVIRONMENT=test pytest -m concurrency
ENVIRONMENT=test pytest tests/test_order_discount.py -q
python -m scripts.verify_db
```

### Test suite performance

The suite ran ~8x slower before two fixes, both worth knowing about if it ever
regresses:

1. **Connection pooling.** The engine forced `NullPool` under test, opening a fresh TCP connection and auth handshake **per statement** — benchmarked at 133 ms/query against Dockerised PostgreSQL versus 4.8 ms pooled. The workaround existed because asyncpg binds a connection to its creating event loop; pinning `asyncio_default_test_loop_scope = session` in `pytest.ini` removes the need for it.
2. **Cleanup strategy.** The per-test fixture truncated all 38 tables unconditionally. `TRUNCATE` rewrites each relation file and syncs the data directory, which benchmarked at a flat ~2.7s regardless of table count. The fixture now detects dirty tables in one query and uses `DELETE` with foreign-key triggers suspended.

Measured on `test_auth.py` (18 tests): **101.4s → 16.2s**. Full suite:
**~45 min projected → 6.6 min**.

### Fixtures

| Fixture | Scope | Purpose |
|---|---|---|
| `_schema` | session, autouse | Drop and create the schema once |
| `_clean_tables` | function, autouse | Reset only dirty tables between tests |
| `client` | function | `httpx.AsyncClient` over the ASGI app — no server needed |
| `seeded` | function | Canonical tenant plus an authenticated `Api` per role |
| `db_session` | context manager | Direct database access for row assertions |

| Helper | Purpose |
|---|---|
| `Api` | Authenticated wrapper; `expect=` fails loudly on an unexpected status |
| `ApiResponse.json()` | Unwraps a `Page` envelope to `items` |
| `ApiResponse.page()` | The full envelope, for asserting `total`/`limit`/`offset` |
| `build_canonical_quote()` | Deal → quote → lines, as the demo does |
| `money()` | Parse an API money string to an exact `Decimal` |
| `page_items()` / `page_total()` | Envelope helpers for direct payloads |
