# BACKEND IMPLEMENTATION PLAN

Derived from [`BACKEND_GAP_ANALYSIS.md`](./BACKEND_GAP_ANALYSIS.md). Ordered by
dependency, not by priority label, because several items unblock others.

## Non-negotiable constraints

The existing architecture is good. This plan is additive.

| Constraint | Reason |
|---|---|
| Do not rewrite working services | `CommercialEngine`, `PolicyEngine`, `DecisionFabric`, `ApprovalService`, `InventoryService` are correct and tested. Extend, never replace. |
| Routers validate and own `commit()` | One visible transaction boundary per endpoint. |
| Services raise typed errors from [`app/errors.py`](../app/errors.py) | Preserves the single error envelope. |
| New enum values go in [`app/enums.py`](../app/enums.py) as `StrEnum` with `enum_col` | VARCHAR + CHECK, so no `ALTER TYPE` migration is ever needed. |
| One Alembic migration per schema change, additive only | No destructive DDL. New columns are nullable or carry a server default. |
| Money stays `Decimal`/`NUMERIC`, serialised as a JSON string | Zero float columns is an asserted invariant. |
| Cross-tenant reads keep returning 404 | Prevents id enumeration. |
| Portal schemas keep having no cost/margin/risk fields | Structural redaction must not regress. |
| Every new mutating endpoint emits an audit event | No service may forget to log. |
| Every new endpoint declares its role dependency | Not an inline body check — see P1-10. |

---

## Stage 0 — security hygiene

Small, and everything else depends on the signing key being real.
Detail in [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md).

| Task | Files |
|---|---|
| Add `.env` and `.venv` to `.gitignore` **before** creating any `.env` | `.gitignore` |
| Create `.env.example` documenting every setting with invalid placeholders | new file |
| Reject the placeholder `jwt_secret_key` when `environment != development` | `app/config.py` |
| Refuse `debug=True` or `cors_origins="*"` in staging/production | `app/config.py` |
| Explicit `CORS_ORIGINS`; `allow_credentials=False`; narrow methods and headers | `app/main.py`, `.env.example` |
| Rate limit `/auth/login`, `/auth/signup`, `/auth/refresh`; return 429 `RATE_LIMITED` with `Retry-After` | new `app/middleware/rate_limit.py`, `app/errors.py` |
| Enforce attention-item ownership on resolve | `app/routers/dashboard.py` |

New error class: `RateLimitedError(status_code=429, code="RATE_LIMITED")`. Add
429 to the `_STATUS_CODES` map in `app/main.py`.

---

## Stage 1 — list contract and pagination (P0-3)

Do this first: it defines the response shape every later list endpoint uses.

**Shared query plumbing** — new `app/schemas/query.py`:

- `PageParams` — `limit` (default 25, 1–200), `offset` (≥0)
- `SortParams` — `sort_by`, `sort_dir` (`asc`/`desc`), validated against a per-endpoint allowlist
- `PeriodParams` — `period` (`today`/`week`/`month`/`quarter`/`year`/`custom`) plus `date_from`/`date_to`, resolving to a concrete range. Reused verbatim by Stage 5 reporting so A7's Period filter and list filters cannot drift.

`Page[T]` already exists in [`app/schemas/common.py`](../app/schemas/common.py)
and is unused — adopt it rather than inventing a new envelope.

**Endpoints converted to `Page[T]`:** `/deals`, `/customers`, `/orders`,
`/products`, `/policies`, `/inventory`, `/audit/events`,
`/dashboard/attention-items`, `/billing/schedules`, `/billing/invoices`.

**Also fix the `list_deals` N+1.** It currently selects every deal, then issues a
`CustomerProfile` fetch plus a quote query per deal. Replace with a join plus an
aggregate subquery for the quote summary.

This is a breaking response-shape change on those routes. No frontend exists
yet, so this is the cheapest moment in the project to make it.

---

## Stage 2 — quotations list (P0-2)

`GET /quotes`, paginated, `InternalUser`.

New `QuoteListItem` schema carrying everything B2's cards need in one payload:
`quote_id`, `quote_number`, `title`, `deal_id`, `deal_reference`,
`customer_profile_id`, `customer_display_name`, `customer_tier`, `status`,
`current_version_id`, `current_version_number`, `current_version_status`,
`total_revenue`, `margin_pct`, `blended_risk_score`, `risk_band`,
`requires_approval`, `is_stale`, `owner_user_id`, `owner_name`, `line_count`,
`age_days`, `last_activity_at`.

Filters: `status`, `version_status`, `owner_user_id`, `customer_profile_id`,
`risk_band`, `is_stale`, `requires_approval`, `q` (search over quote number,
title, customer name), plus `PeriodParams`.

Single query joining `quotes` → `quote_versions` (current) → `deals` →
`customer_profiles` → `users`. `margin_pct` and `blended_risk_score` come from
the current version, so `SALES` sees margin here — correct, since only
`/portal/*` is redacted.

Also add `GET /deals` a `stage` filter for the Kanban view (B1.2).

---

## Stage 3 — per-organization settings (P0-9 part 1)

Unblocks Stage 4 anomaly detection and B9.1's configurable stalled window.

New table `organization_settings`, one row per organization:

| Column | Type | Default | Purpose |
|---|---|---|---|
| `organization_id` | UUID FK, unique | — | Tenant |
| `stalled_deal_days` | INTEGER | 14 | B9.1 "configured number of days" |
| `finance_escalation_threshold` | NUMERIC(9,4) | 60.0 | A3.3 |
| `risk_discount_overage_weight` | NUMERIC(9,4) | 3.0 | Risk C1 |
| `risk_breadth_weight` | NUMERIC(9,4) | 5.0 | Risk C2 |
| `risk_margin_weight` | NUMERIC(9,4) | 5.0 | Risk C3 |
| `risk_depth_weight` | NUMERIC(9,4) | 0.4 | Risk C4 |
| `discount_anomaly_sigma` | NUMERIC(9,4) | 2.0 | Anomaly `k` |
| `discount_anomaly_min_samples` | INTEGER | 5 | Baseline trust floor |
| `approval_sla_hours` | INTEGER | 24 | W13 |
| `recommendation_min_margin_pct` | NUMERIC(9,4) | 0.0 | A6.3 |

`OrganizationSettingsService.for_org` returns the row, creating it from
`app.config` defaults on first access so existing tenants keep current
behaviour. `PolicyEngine` and `DashboardService` read from it with the env value
as fallback — so nothing breaks if the row is absent.

Endpoints: `GET /admin/settings`, `PATCH /admin/settings` (`AdminUser`).

Replaces the `NO_RESPONSE_DAYS = 14` module constant in
`dashboard_service.py`.

---

## Stage 4 — order-level discount (P0-7)

Do this before reporting, because it changes what "total discount" means.

Add to `quote_versions`: `order_discount_pct NUMERIC(9,4) NOT NULL DEFAULT 0`
and `order_discount_amount NUMERIC(18,2) NOT NULL DEFAULT 0` (derived).

**The critical design decision.** The order-level discount is **distributed
pro-rata across lines by revenue share** before per-line ceiling evaluation.
Applying it only to the grand total would let a rep move discount from lines to
the order and route around per-line ceilings entirely — precisely the loophole
PDF §10 warns about ("keeping every line technically within limits while still
discounting the order more than the company intends").

`CommercialEngine`:
1. Compute line-level amounts as today.
2. Apply `order_discount_pct` to `net_revenue`, producing `order_discount_amount`.
3. Distribute that amount across lines by `net_amount / net_revenue` to produce an `effective_line_discount_pct` per line.
4. Recompute tax on the post-order-discount net.
5. `effective_discount_pct = (total_line_discount + order_discount_amount) / gross_revenue × 100`.

`PolicyEngine` evaluates ceilings against the **effective** per-line discount, so
component C1 and the signing-authority policy both see the true giveaway.

Schema changes: `order_discount_pct` on `QuoteCreate` and `RevisionCreate`; new
`PATCH /quote-versions/{id}/discount` (`SalesUser`, `DRAFT` only). Add
`order_discount_pct` to `DecisionFabric`'s material-field list with a 0.01pp
epsilon.

**Test carefully.** Existing canonical-flow assertions must be unchanged when
`order_discount_pct = 0`.

---

## Stage 5 — discount anomaly detection (P0-4)

New `app/services/anomaly_service.py`:

```
baseline(session, user_id, organization_id) -> RepDiscountBaseline
    sample = effective_discount_pct of that rep's recent submitted versions
    return mean, stdev, count, window
```

Flag when `count >= min_samples` and
`value > mean + sigma * stdev`. Severity by magnitude: ≥3σ CRITICAL, ≥2σ HIGH,
else MEDIUM.

New `AttentionItemType.DISCOUNT_ANOMALY`, owner `MANAGER`. Evaluated inside
`DecisionFabric.process_version` so it reuses the existing decision-point timing
and the anti-spam partial unique index.

**The `reason` must state the arithmetic** — for example
*"17.47% effective discount is 3.2 standard deviations above Sam Rivera's
12-quote average of 6.4%"*. A bare flag would contradict the explainability
standard the rest of the system holds.

Also expose `GET /reports/discount-anomalies`.

---

## Stage 6 — delivery promise and slippage (P0-8)

| Change | Detail |
|---|---|
| `sales_orders.promised_delivery_date` | DATE nullable |
| `sales_order_lines.promised_delivery_date` | DATE nullable, per-line override |
| `fulfillments.delivered_at` | Already exists; make it reachable |
| `POST /orders/{id}/fulfillments/{fid}/deliver` | `OpsUser`; sets `DELIVERED`, emits `ORDER_DELIVERED` |
| `PATCH /orders/{id}/promise` | `OpsUser`/`SalesUser`; sets the promised date |
| Slippage rule | Undelivered and `promised_delivery_date < today`, or backordered with `expected_available_at > promised_delivery_date` |
| `AttentionItemType.DELIVERY_SLIPPAGE` | Owner `OPS`, severity by days late |
| Deal-health signal | `DELIVERY_SLIPPAGE`, −10 |

New event: `ORDER_DELIVERED`.

---

## Stage 7 — attention-item actions (P0-9 part 2)

| Endpoint | Effect |
|---|---|
| `POST /dashboard/attention-items/{id}/acknowledge` | `OPEN` → `ACKNOWLEDGED`; records who and when. Makes the existing unreachable enum value real |
| `POST /dashboard/attention-items/{id}/nudge` | Increments `nudge_count`, sets `last_nudged_at`, records the target role, emits `ATTENTION_ITEM_NUDGED` |
| `POST /dashboard/attention-items/{id}/escalate` | Raises `severity` one band, optionally reassigns `owner_role`, emits `ATTENTION_ITEM_ESCALATED` |

New columns on `attention_items`: `acknowledged_at`, `acknowledged_by_user_id`,
`nudge_count` (default 0), `last_nudged_at`, `escalated_at`,
`escalated_by_user_id`, `escalation_note`.

New events: `ATTENTION_ITEM_ACKNOWLEDGED`, `ATTENTION_ITEM_NUDGED`,
`ATTENTION_ITEM_ESCALATED`.

Restrict all three plus `resolve` to the item's `owner_role`, its
`owner_user_id`, or `ADMIN` (SEC-6).

---

## Stage 8 — reporting module (P0-1)

The largest single item. Consumes `PeriodParams` from Stage 1 and the anomaly
data from Stage 5.

**Sales teams** — new `sales_teams` table (`name`, `code` unique per org,
`manager_user_id`, `is_active`) and `sales_team_members`
(`sales_team_id`, `user_id`, unique pair). Endpoints: `POST`/`GET`/`PATCH
/admin/sales-teams`, `POST`/`DELETE /admin/sales-teams/{id}/members`. Without
this, A7.4's "Sales Team" filter has no subject.

**`app/services/reporting_service.py`** — aggregate queries only, no row-by-row
Python:

| Endpoint | Content | PDF |
|---|---|---|
| `GET /reports/sales-performance` | Quote count, order count, gross/net revenue, margin, margin %, avg discount, win rate, grouped by `rep`/`team`/`month`/`customer`/`tier` | A7.1 |
| `GET /reports/approval-status` | Counts and value by approval state, avg time-to-decision, SLA breaches | A7.5 |
| `GET /reports/products` | Best-selling by units and revenue; most-discounted by avg discount and total given away; margin contribution | A7.6 |
| `GET /reports/discounts` | Distribution by rep, band histogram, ceiling-breach frequency, anomaly list | A7.6, B9.2 |
| `GET /reports/pipeline` | Deal count and value by stage, conversion between stages | A7.1 |

Every report accepts: `PeriodParams`, `rep_user_id`, `team_id`,
`approval_status`, `product_id`, `category`, `customer_profile_id`,
`group_by`. All `InternalUser`.

**Export** — `GET /reports/{report_name}/export?format=xlsx|csv|pdf`:

- `csv` — stdlib `csv`, zero dependency
- `xlsx` — `openpyxl`
- `pdf` — `reportlab`

Returned as a `StreamingResponse` with `Content-Disposition: attachment`. This
introduces the **first binary responses in the API**, which must be documented
separately in [`BACKEND_API_DOCUMENTATION.md`](./BACKEND_API_DOCUMENTATION.md)
since every existing response is JSON.

Add `openpyxl` and `reportlab` to `requirements.txt`.

---

## Stage 9 — subscription lifecycle (P0-5, P0-6)

The second-largest item, and the one with the most PDF references.

### 9a — apply a mid-cycle change

`POST /billing/subscriptions/{schedule_id}/change`, `FINANCE`/`ADMIN`:

```
{ "new_quantity": "5", "new_interval": "MONTHLY", "effective_date": "2026-07-01", "reason": "..." }
```

Logic:
1. Reject if the target period is already `INVOICED` → 409 `PERIOD_ALREADY_INVOICED`.
2. Prorate the current period at `effective_date` using the existing `BillingService.prorate`.
3. Split the current period into an old-rate prorated part and a new-rate prorated part.
4. Regenerate future periods at the new quantity/interval.
5. Leave invoiced history untouched.
6. Emit `SUBSCRIPTION_CHANGED`.

New status: make `BillingScheduleStatus.ACTIVE` reachable for the current period.

### 9b — cancel with credit note

New table `credit_notes`:

| Column | Notes |
|---|---|
| `credit_note_number` | `CN-00001`, unique per org |
| `sales_order_id`, `invoice_id` (nullable), `billing_schedule_id` (nullable), `customer_organization_id` | Links |
| `status` | New `CreditNoteStatus`: `DRAFT` `ISSUED` `APPLIED` `VOID` |
| `subtotal`, `tax_amount`, `total_amount` | `CHECK >= 0` |
| `reason` | TEXT NOT NULL |
| `issued_at`, `issued_by_user_id` | Attribution |

`POST /billing/subscriptions/{schedule_id}/cancel`, `FINANCE`/`ADMIN`:

1. Future `SCHEDULED` periods → `CANCELLED`.
2. Current period: prorate the **unused** portion from `effective_date`.
3. If the current period is invoiced and paid, issue a credit note for the unused amount and set `PaymentStatus.REFUNDED` where a refund is actually made.
4. If invoiced and unpaid, reduce or void the invoice.
5. Emit `SUBSCRIPTION_CANCELLED` and `CREDIT_NOTE_ISSUED`.

Also: `GET /billing/credit-notes`, `GET /billing/credit-notes/{id}`,
`POST /billing/credit-notes/{id}/void`.

New events: `SUBSCRIPTION_CHANGED`, `SUBSCRIPTION_CANCELLED`,
`CREDIT_NOTE_ISSUED`.

New errors: `PERIOD_ALREADY_INVOICED`, `SUBSCRIPTION_NOT_RECURRING`,
`EFFECTIVE_DATE_OUTSIDE_PERIOD`.

---

## Stage 10 — finish the dead features (P1)

| Task | Detail |
|---|---|
| **Variants usable** | Add `product_variant_id` to `QuoteLineCreate`/`QuoteLineUpdate`; validate the variant belongs to the product **and** the organization; apply `price_delta`/`cost_delta` in `CommercialEngine`; carry it into `sales_order_lines`; add `GET /admin/product-variants` and `GET /products/{id}/variants` |
| **Price lists live** | `PriceListService.resolve_unit_price(product, profile, on_date)` reads `rules` JSONB matching tier and validity window; `QuoteService.add_line` uses it before falling back to `product.list_price`; an explicit `unit_list_price` override still wins; add `GET`/`PATCH /admin/price-lists` |
| **Promoted products** | `products.is_promoted` BOOLEAN default false; `RecommendationEngine` boosts promoted candidates and returns `is_promoted` so B5 can render the tag; expose in `ProductUpdate` |
| **Dismiss persists** | `dismissed_recommendations` table (`quote_version_id`, `product_id`, `dismissed_by_user_id`, unique triple); `POST /quotes/{id}/recommendations/{product_id}/dismiss`; filter dismissed from results |
| **Recommendation margin floor** | Honour `recommendation_min_margin_pct` from Stage 3 settings |
| **Warehouse CRUD** | `GET /warehouses/{id}`, `PATCH /admin/warehouses/{id}`, deactivate via `is_active` |
| **Quote lose** | `POST /quotes/{id}/lose` with reason → `QuoteStatus.LOST`, deal → `CLOSED_LOST`, retire attention items, emit `QUOTE_LOST` |
| **Order cancel** | `POST /orders/{id}/cancel` → release reservations (`AllocationStatus.RELEASED`, decrement `quantity_reserved`), cancel schedules, order → `CANCELLED`, emit `ORDER_CANCELLED` |
| **Invoice void / overdue** | `POST /billing/invoices/{id}/void`; compute `OVERDUE` on read when `due_date < today` and not paid |
| **Deal stage guard** | Validate against an allowed-transition map; reject reverting from a closed stage |
| **Declared authorization** | Replace the inline role checks in `orders.py` and `billing.py` with `OpsUser` and a new `FinanceUser`, so restrictions appear in OpenAPI |
| **Seed a payment-terms policy** | The `PAYMENT_TERMS_LIMIT` evaluator is fully built and never fires; one seed row exercises it |

---

## Stage 11 — differentiators (P2)

| Task | Detail |
|---|---|
| **What-if simulation** | `POST /quote-versions/{id}/simulate` taking hypothetical line changes plus `order_discount_pct`, returning would-be totals, risk decomposition, band and required approvers. **Writes nothing.** `PolicyEngine.evaluate` and `CommercialEngine.calculate_line` are already pure, so this clones loaded lines in memory and calls them |
| **Co-purchase recommendations** | Attach-rate aggregate over `sales_order_lines` (pair support and confidence), blended with margin ranking, with the existing heuristics as a documented cold-start fallback |
| **Deal replay** | `GET /quotes/{id}/replay` assembling `commercial_snapshots` + `approval_decisions.decision_snapshot` + `decision_impacts` + `audit_events` into an ordered timeline of states |
| **Reorder alerts** | `INVENTORY_REORDER_NEEDED` attention item when `quantity_available < reorder_point`, owner `OPS` |
| **Approval SLA** | Compare `waiting_since` against `approval_sla_hours`; surface breaches in the inbox and `GET /reports/approval-status` |

---

## Stage 12 — tests

Extend, do not replace. Target: every new endpoint has success, authorization
and validation coverage; every new state transition has a legal and an illegal
case.

| New file | Covers |
|---|---|
| `tests/test_pagination.py` | `Page[T]` envelope, limit bounds, offset, sort allowlist rejection, period resolution |
| `tests/test_quote_list.py` | `GET /quotes` fields, every filter, search, tenant isolation |
| `tests/test_reporting.py` | Each report's arithmetic against hand-computed seed values; every filter; each export format's content type and headers |
| `tests/test_sales_teams.py` | Team CRUD, membership, team-filtered reports |
| `tests/test_organization_settings.py` | Defaults on first access, patch, `PolicyEngine`/`DashboardService` honouring overrides |
| `tests/test_order_discount.py` | Pro-rata distribution, ceiling evaluation against effective discount, **the routing loophole is closed**, zero-discount regression |
| `tests/test_anomaly.py` | Baseline maths, min-sample suppression, sigma thresholds, severity banding, attention item reason text |
| `tests/test_delivery_slippage.py` | Promise dates, delivered transition, slippage detection, health signal |
| `tests/test_attention_actions.py` | Acknowledge, nudge, escalate, ownership enforcement (SEC-6) |
| `tests/test_subscription_lifecycle.py` | Mid-cycle change proration, invoiced-period rejection, future regeneration, cancellation, credit note amounts, refund status |
| `tests/test_credit_notes.py` | Issue, void, invoice linkage, amount ceilings |
| `tests/test_variants_pricelists.py` | Variant attach and delta pricing, cross-org rejection, tier price resolution, explicit override precedence |
| `tests/test_simulation.py` | Simulation matches a real submit's numbers, and **persists nothing** |
| `tests/test_security_hardening.py` | Rate limit 429 + `Retry-After`, CORS origin rejection, config validators |

Also extend `tests/test_rbac.py` for every new endpoint × role, and
`tests/test_end_to_end.py` with a second flow exercising order-level discount,
a subscription change, and a cancellation with credit note.

---

## Stage 13 — documentation from verified payloads

1. Run the canonical flow against the live database so real data exists.
2. Capture actual responses for every endpoint, including the new ones.
3. Write [`BACKEND_API_DOCUMENTATION.md`](./BACKEND_API_DOCUMENTATION.md) from captured payloads, not from schemas — including the new binary export responses.
4. Write [`FRONTEND_INTEGRATION_GUIDE.md`](./FRONTEND_INTEGRATION_GUIDE.md) with the API client structure, TypeScript interfaces, auth state, error mapping, loading states.
5. Write [`API_TEST_CASES.md`](./API_TEST_CASES.md) with request, expected response, expected database change, unauthorized behaviour and invalid-input behaviour per workflow.
6. Save `docs/openapi.json` and document the `openapi-typescript` command.
7. Update `README.md` for the new modules and refresh the endpoint map.

---

## Migration sequence

Additive only. Each is a separate Alembic revision so any one can be rolled back
independently.

| # | Revision | Changes |
|---|---|---|
| M1 | `organization_settings` | New table, seeded from config defaults on first read |
| M2 | `order_discount` | `quote_versions.order_discount_pct`, `.order_discount_amount`, both `NOT NULL DEFAULT 0` |
| M3 | `delivery_promise` | `sales_orders.promised_delivery_date`, `sales_order_lines.promised_delivery_date`, both nullable |
| M4 | `attention_actions` | Seven new nullable columns plus `nudge_count NOT NULL DEFAULT 0` |
| M5 | `sales_teams` | `sales_teams`, `sales_team_members` |
| M6 | `credit_notes` | `credit_notes` table |
| M7 | `promoted_and_dismissed` | `products.is_promoted NOT NULL DEFAULT false`, `dismissed_recommendations` table |

`scripts/verify_db.py` must be updated: the expected table count moves from 33 to
**37** (`organization_settings`, `sales_teams`, `sales_team_members`,
`credit_notes`, `dismissed_recommendations` = 38 — recount at implementation
time and update `EXPECTED_TABLES` in `app/models/__init__.py` to match, since a
test asserts it).

Run `alembic check` after each revision to confirm models and schema agree.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Order-level discount breaks canonical-flow assertions | Default 0 must be a no-op. Assert the existing 132,710.00 / 24.4970% numbers are unchanged before touching anything else |
| Pagination is a breaking change | Do it in Stage 1, before any frontend exists |
| Order discount opens a governance loophole | Distribute pro-rata across lines **before** ceiling evaluation; write the loophole test first |
| Reporting aggregates get slow | Aggregate in SQL, never in Python; the existing composite indexes on `(organization_id, status)` cover most paths |
| `EXPECTED_TABLES` test fails after migrations | Update the constant in the same commit as each migration |
| Subscription proration corrupts invoiced history | Reject changes to `INVOICED` periods outright; only future and current-uninvoiced periods are mutable |
| Scope overrun | Stages 0–9 are P0. If time runs out, stop after Stage 9 and document Stages 10–11 as next steps — PDF §8 asks for that note anyway |

---

## Definition of done

- `ENVIRONMENT=test pytest` fully green, including the canonical end-to-end flow
- `python -m scripts.verify_db` passes with the updated table count
- `alembic check` reports no drift
- Every PDF module A1–A7 and B1–B9 is IMPLEMENTED or has a documented, justified deferral
- All eight Quick Test Flow steps demonstrable
- Stage 0 security items closed
- All 15 documentation files present and written from verified payloads
- An explicit backend readiness verdict recorded
