# BACKEND GAP ANALYSIS

> **Status: closed.** This document was written as an audit of the backend as
> found. Every P0 and P1 item below has since been implemented, and two P2
> differentiators were delivered as well. The original analysis is retained
> unedited because it is the reasoning that justified the work; §"Resolution"
> at the end records what shipped. Verified by 433 passing tests.

Priorities:

| Level | Meaning |
|---|---|
| **P0** | The product cannot correctly satisfy the PDF without this |
| **P1** | Very important for complete real-world functionality |
| **P2** | Strong differentiator / judge-impact feature |
| **P3** | Nice to have |
| **REJECT** | Unnecessary or harmful overengineering |

Each gap is scored against seven questions: mandatory for the problem, important
for realistic use, useful for judging, required for frontend integration,
security requirement, edge-case requirement, unnecessary complexity.

---

## Summary

| Priority | Count | Estimated effort |
|---|---|---|
| P0 | 9 | Substantial — one whole module plus one lifecycle |
| P1 | 11 | Mostly finishing dead code and filling CRUD holes |
| P2 | 7 | Differentiators |
| P3 | 4 | Cleanup |
| REJECT | 8 | Explicitly do not build |

**Headline.** The backend's hard engine work is done to a standard well above
typical hackathon output. The gaps cluster in three places: a module that was
never started (A7 reporting), a lifecycle that stops at the calculator (A5/B7
subscriptions), and the list/query plumbing every frontend needs.

---

## P0 — blocking

### P0-1 · Reporting and analytics module (A7) does not exist

| Question | Answer |
|---|---|
| Mandatory for the problem? | **Yes** — A7 is a lettered module with six explicit sub-requirements |
| Important for realistic use? | Yes — a sales platform without sales reporting is not one |
| Useful for judging? | **Yes** — an entire missing module is the easiest thing for a judge to notice |
| Required for frontend? | Yes — B1 lists "Dashboard plus reporting menu" |
| Security requirement? | No |
| Edge case? | No |
| Unnecessary complexity? | No |

**Evidence.** No `/reports/*` route exists in the 78-operation route table.
`/dashboard/*` covers deal health and the attention queue, which is an
operational action queue — a different artifact from sales performance analytics.

**Required work.**
- `app/services/reporting_service.py` with aggregate queries over `quote_versions`, `sales_orders`, `sales_order_lines`, `approval_requests`
- `sales_teams` table plus membership, so the "Sales Team" filter has a subject
- `GET /reports/sales-performance` — revenue, margin, discount, win rate, by rep and team
- `GET /reports/approval-status` — pipeline counts by approval state
- `GET /reports/products` — best-selling and most-discounted
- `GET /reports/discounts` — discount distribution per rep, which also feeds P0-4
- Filters on all: `period` (`today`/`week`/`month`/`custom` with `date_from`/`date_to`), `rep_user_id`, `team_id`, `approval_status`, `product_id`, `category`
- Export: `GET /reports/{report}/export?format=xlsx|pdf`

**Note on export.** XLSX needs `openpyxl`; PDF needs `reportlab`. Both are
small, pure-Python additions. If time is short, ship XLSX and CSV and document
PDF as the deferred item — but A7 names PDF explicitly, so it stays P0.

---

### P0-2 · No flat quotations list endpoint (B1/B2)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — B1 "Quotations: redirects to the list of active and draft quotations" |
| Required for frontend? | **Yes, blocking.** The Quotations screen and Kanban pipeline are the workspace entry point |

**Evidence.** Only `GET /quotes/{quote_id}` exists. To render a quote list the
frontend must call `GET /deals` and read the nested `quotes[]`, where
`DealQuoteSummary` carries `quote_number`, `title`, `status` and
`current_version_number` — but **no amount**, which B2 explicitly requires
("cards showing customer, amount, and stage").

**Required work.** `GET /quotes` returning per quote: `quote_id`,
`quote_number`, `title`, `customer_display_name`, `deal_reference`, `status`,
`current_version_status`, `total_revenue`, `margin_pct`, `blended_risk_score`,
`risk_band`, `is_stale`, `requires_approval`, `owner_user_id`, `owner_name`,
`age_days`, `last_activity_at`. Filters: `status`, `version_status`, `owner`,
`customer`, `risk_band`, `stale`, `q` (search on number/title/customer).
Paginated and sortable.

---

### P0-3 · No pagination, filtering or sorting anywhere

| Question | Answer |
|---|---|
| Mandatory? | Implied — A7's filters and B2's list are unusable without it |
| Required for frontend? | **Yes, blocking** |
| Edge case? | Yes — behaviour at realistic data volume |

**Evidence.** `Page[T]` is defined in
[`app/schemas/common.py`](../app/schemas/common.py) with `items`, `total`,
`limit`, `offset` and is **never imported anywhere**. Only `GET /orders` accepts
`limit`. `list_deals` in [`app/routers/deals.py`](../app/routers/deals.py)
selects every deal in the organization and then issues a `CustomerProfile` fetch
plus a quote query **per deal** — an unbounded N+1.

**Required work.** Adopt `Page[T]` across `/deals`, `/quotes`, `/customers`,
`/orders`, `/products`, `/policies`, `/audit/events`,
`/dashboard/attention-items`, `/billing/schedules`, `/billing/invoices`. Add
`limit`/`offset`, `sort_by`/`sort_dir`, and entity-appropriate filters. Fix the
`list_deals` N+1 with eager loading and an aggregate subquery.

**Breaking change.** Switching a list response from a bare array to
`{items, total, limit, offset}` changes the contract. Since no frontend exists
yet, this is the cheapest moment in the project's life to do it.

---

### P0-4 · Discount anomaly detection vs rep baseline (B9)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — B9 names it explicitly |
| Useful for judging? | **Very** — it is a behavioural signal, not a threshold check, and hard to fake convincingly |
| Edge case? | No — it is a core signal |

**Evidence.** No per-rep baseline is computed anywhere. `PolicyEngine` detects
breaches of an **absolute** ceiling. The PDF asks for something different: *"a
discount well above a rep's historical average."* A rep whose historical average
is 4% suddenly quoting 14% is an anomaly even though 14% is inside a 15%
ceiling — and the current system is structurally blind to it.

This is the clearest case in the audit where the PDF asks for a deeper idea than
the implementation has.

**Required work.**
- `RepDiscountBaseline` computed from that rep's recent submitted versions: mean and standard deviation of `effective_discount_pct`, plus a sample count
- Deviation rule: flag when `effective_discount_pct > mean + k * stdev` with a configurable `k`, and a minimum sample size before the baseline is trusted
- `AttentionItemType.DISCOUNT_ANOMALY`, owner `MANAGER`, severity by deviation magnitude
- Evaluated at submit time inside `DecisionFabric.process_version`
- Surfaced in `GET /reports/discounts` and the Control Tower
- The attention item must state the arithmetic: *"18% is 3.2 standard deviations above Sam Rivera's 12-quote average of 6.4%"* — a bare flag would not be defensible

---

### P0-5 · Mid-cycle subscription change is preview-only (A5/B7)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — named in A5 *and* B7 |
| Important for realistic use? | Yes — subscriptions change constantly |

**Evidence.** `BillingService.prorate` implements exact day-counted proration
with both endpoints inclusive, verified live:

```json
{"days_in_period":365,"days_billed":184,"proration_factor":"0.50410959","prorated_amount":"604.93"}
```

It is exposed **read-only** at `GET /billing/proration-preview`. No endpoint
applies a change. `BillingScheduleStatus.ACTIVE` is unreachable.

The maths is a calculator, not a workflow.

**Required work.** `POST /billing/subscriptions/{schedule_id}/change` accepting
`new_quantity` or `new_interval` plus `effective_date`: prorate the current
period, regenerate future periods, preserve invoiced history immutably, emit an
audit event. Guard against changing an already-invoiced period.

---

### P0-6 · Subscription cancellation and credit notes (A5/B7)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — named in A5 *and* B7 |
| Useful for judging? | Yes — QT-adjacent and visibly absent |

**Evidence.** Entirely absent. No `credit_notes` table, no cancel endpoint.
`BillingScheduleStatus.CANCELLED` and `PaymentStatus.REFUNDED` both exist in the
enums and are unreachable — the schema anticipated this feature and it was never
built.

**Required work.**
- `credit_notes` table: number, `sales_order_id`, `invoice_id` (nullable), `billing_schedule_id` (nullable), `customer_organization_id`, `status`, `amount`, `tax_amount`, `total_amount`, `reason`, `issued_at`, `issued_by_user_id`
- `POST /billing/subscriptions/{schedule_id}/cancel` with `effective_date` and `reason`
- Unused-period proration to compute the refundable amount
- Future schedules → `CANCELLED`; current period prorated
- Credit note issued against the paid invoice; `PaymentStatus.REFUNDED` reachable
- Alembic migration, no destructive DDL

---

### P0-7 · Order-level discount (B3)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — B3 says "line level **or order level** discounts" |
| Required for frontend? | Yes — the builder needs the control |

**Evidence.** Only `quote_lines.discount_pct` exists. There is no order-level
discount anywhere in the model, engine or schemas.

**Required work.** Add `order_discount_pct` (and/or `order_discount_amount`) to
`quote_versions`. `CommercialEngine` must apply it after line discounts and
before tax, and — importantly — `PolicyEngine` must fold it into
`effective_discount_pct` so component C4 and the signing-authority policy still
see the true total giveaway. Getting this wrong would let a rep route around
governance by moving the discount from lines to the order.

**Design note.** Distributing the order discount pro-rata across lines by
revenue share keeps per-line ceiling checks meaningful; applying it only at the
total would create exactly the loophole PDF §10 warns about.

---

### P0-8 · Delivery promise dates and slippage (B9)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — B9 "Delivery promise slippage indicators" |
| Edge case? | No — it is a named dashboard signal |

**Evidence.** No promised delivery date exists on `sales_orders`,
`sales_order_lines` or `fulfillments`. `FulfillmentStatus.DELIVERED` is
unreachable, so even actual delivery cannot be recorded. There is nothing to
measure slippage against.

**Required work.** `promised_delivery_date` on the order (and optionally per
line), `POST /orders/{id}/fulfillments/{fid}/deliver` to reach `DELIVERED`, a
slippage computation (promised vs projected/actual), a
`DELIVERY_SLIPPAGE` attention type owned by `OPS`, and a deal-health signal.

---

### P0-9 · Nudge and escalate actions, and per-tenant thresholds (A3/B9)

| Question | Answer |
|---|---|
| Mandatory? | **Yes** — B9 "An automated nudge or escalation action can be triggered from an alert"; A3 configurable chain; B9 "configured number of days" |
| Required for frontend? | Yes — the alert card needs actions beyond Resolve |

**Evidence.**
- `POST /dashboard/attention-items/{id}/resolve` is the only action.
- `AttentionItemStatus.ACKNOWLEDGED` is unreachable, so there is no "seen, working on it" state.
- `NO_RESPONSE_DAYS = 14` is a module constant in `dashboard_service.py`.
- `risk_finance_escalation_threshold` and the four risk weights are process-global environment variables, not per-organization.

**Required work.**
- `organization_settings` table: `stalled_deal_days`, `finance_escalation_threshold`, risk weights, anomaly `k`, minimum baseline sample
- `GET`/`PATCH /admin/settings` for `ADMIN`
- `PolicyEngine` and `DashboardService` read per-tenant settings with the env value as fallback
- `POST /dashboard/attention-items/{id}/acknowledge`
- `POST /dashboard/attention-items/{id}/nudge` — records a nudge, increments a counter, audits it
- `POST /dashboard/attention-items/{id}/escalate` — raises severity, reassigns `owner_role`, audits it

---

## P1 — important

| ID | Gap | Evidence | Required work |
|---|---|---|---|
| P1-1 | **Product variants unusable** | `quote_lines.product_variant_id` exists and is copied on revision, but `QuoteLineCreate` has no such field | Add `product_variant_id` to `QuoteLineCreate`/`QuoteLineUpdate`; validate parentage; apply `price_delta`/`cost_delta` in `CommercialEngine`; add `GET /admin/product-variants` and `GET /products/{id}/variants` |
| P1-2 | **Price lists inert** | `price_lists.rules` written by `POST /admin/price-lists`, never read | Resolve tier price in `QuoteService.add_line` before falling back to `product.list_price`; add `GET`/`PATCH /admin/price-lists` |
| P1-3 | **No promoted products** | No `is_promoted` column | Add the column; boost promoted items in `RecommendationEngine`; return a `promotion` flag so B5 can render the tag |
| P1-4 | **Dismiss not persisted** | B5 requires Dismiss; nothing stores it | `dismissed_recommendations` table or a JSONB set on the version; filter dismissed items out |
| P1-5 | **Warehouse edit missing** | `POST /admin/warehouses` only | `GET /warehouses/{id}`, `PATCH`, soft-delete via `is_active` |
| P1-6 | **Quote cannot be marked lost** | `QuoteStatus.LOST`/`CANCELLED` unreachable; `DealStage.CLOSED_LOST` only via manual PATCH | `POST /quotes/{id}/lose` with a reason; set deal stage; audit |
| P1-7 | **Order cannot be cancelled** | `SalesOrderStatus.CANCELLED` read but never set; `AllocationStatus.RELEASED` unreachable | `POST /orders/{id}/cancel` releasing reservations back to stock and cancelling schedules |
| P1-8 | **Invoice void and overdue unreachable** | `InvoiceStatus.VOID` read but never set; `OVERDUE` never computed | `POST /billing/invoices/{id}/void`; compute `OVERDUE` on read when `due_date` has passed |
| P1-9 | **Deal stage transitions unguarded** | `PATCH /deals/{id}` accepts any `DealStage`, so `CLOSED_WON` can revert to `QUALIFICATION` | Validate against an allowed-transition map |
| P1-10 | **Inline authorization invisible to OpenAPI** | `OpsUser` defined but unused; `orders.py` and `billing.py` check roles inside handler bodies | Replace inline checks with declared dependencies so generated clients and `/docs` show the real restrictions |
| P1-11 | **Attention item ownership unenforced** | Any internal role can resolve a `CRITICAL` item owned by `FINANCE` | Restrict resolve to the owner role or `ADMIN` |

---

## P2 — differentiators

| ID | Feature | Why it earns credit |
|---|---|---|
| P2-1 | **What-if simulation** — `POST /quote-versions/{id}/simulate` evaluating a hypothetical discount without persisting | `PolicyEngine.evaluate` is already pure, so this is mostly plumbing. Turns the risk score from a verdict into a planning tool, and demos beautifully: move a slider, watch the required approvers change |
| P2-2 | **Co-purchase-derived recommendations** | Replaces the heuristic with real attach-rate mining over `sales_order_lines`. Directly satisfies A6.1 and makes QT4 substantive |
| P2-3 | **Deal replay / autopsy** — reconstruct any past state from `commercial_snapshots` + `audit_events` | The data is already there. Answers "what was true when this was approved?" — the exact question the staleness feature exists to prevent |
| P2-4 | **Reorder-point alerts** | `inventory.reorder_point` is stored and nothing acts on it. Completes A4.3 cheaply |
| P2-5 | **Seed a `PAYMENT_TERMS_LIMIT` policy** | The evaluator is fully implemented and never fires. One seed row demonstrates a fourth policy type at zero code cost |
| P2-6 | **Approval SLA tracking** | `waiting_since` is already in the inbox payload; add an SLA threshold and surface breaches |
| P2-7 | **Configurable minimum-margin floor for recommendations** | Completes A6.3 |

---

## P3 — cleanup

| ID | Item | Note |
|---|---|---|
| P3-1 | Prune expired idempotency keys | `expires_at` is written, nothing deletes. Add a maintenance endpoint or documented job |
| P3-2 | Remove unused schemas | `QuoteVersionTotals`, `ProductPublicRead`, `OrganizationRead`, `OrganizationCreate`, `RoleRead`, `UserSummary`, `MessageResponse` are defined and never referenced |
| P3-3 | Remove or use `TenantIsolationError` | Defined, never raised; cross-tenant correctly returns 404 instead |
| P3-4 | `NegotiationThread.CLOSED` unreachable | `RESOLVED` covers the real case; either wire it or drop it |

---

## REJECT — do not build

| Item | Reason |
|---|---|
| Multi-currency FX conversion | PDF §7: "a bonus, not a requirement". Correctly-rounded multi-currency arithmetic is a large surface for near-zero credit |
| Message broker (Kafka/RabbitMQ) | The in-process bus runs handlers on the caller's session so audit and state commit together. A broker would **break** that guarantee to solve a problem this system does not have |
| Redis / caching layer | No read path is hot enough to justify cache invalidation on governed financial data |
| File upload / object storage | Zero PDF requirements involve uploads. Verified: no `UploadFile`, `FileResponse` or `StreamingResponse` in the codebase |
| WebSockets / SSE | "Real time" in the PDF means recomputed-on-read. Refetch-on-action plus optional polling satisfies every stated requirement at a fraction of the complexity |
| ML / predictive scoring models | PDF §7 stresses defensible business logic. A black box weakens the demo — a judge asking "why did it score 32?" must get an arithmetic answer |
| Payment gateway integration | QT8 requires *recording* a payment and updating invoice status, not processing one |
| Customer-facing PDF quote generation | The PDF explicitly positions the portal as the replacement for "a static PDF". A7's export requirement is for *reports*, not quotes |

---

## Real-user simulation (Phase 6)

Each scenario run against the actual code. Weaknesses feed the priority list.

| Scenario | Current behaviour | Verdict |
|---|---|---|
| Submits invalid data | 422 with `details.errors[]` carrying `loc`, `msg`, `type`, `input`, `ctx` | **Solid** — enough for field-level UI errors |
| Refreshes the page mid-build | All totals are server-side; nothing is client-held | **Solid** |
| Loses internet after POST commits | Retry with the same `Idempotency-Key` replays the stored response | **Solid** on confirm and allocate; other POSTs rely on uniqueness constraints |
| Retries a request | Idempotent on the two mutating money paths | **Solid** |
| Double-clicks submit | Second call gets 409 (`VERSION_NOT_DRAFT`, `NO_PENDING_STEP`, or `ALREADY_CONFIRMED`) | **Solid** |
| Submits the same action twice | `UNIQUE (sales_orders.quote_version_id)` makes duplicate orders impossible | **Solid** |
| Accesses an unauthorized resource | 403 with `your_role` and `allowed_roles`, or 404 cross-tenant | **Solid** |
| Modifies after submission | 409 `IMMUTABLE_VERSION` with `editable_statuses` and guidance | **Solid** |
| Deletes something with dependencies | FK `ON DELETE RESTRICT`; no delete endpoints on commercial entities | **Acceptable** — but there is also no way to void an order or lose a quote (P1-6, P1-7) |
| Uploads an invalid or huge file | No upload path exists | **N/A** |
| Abandons a workflow halfway | A `DRAFT` version sits forever; `PENDING_APPROVAL` raises an attention item | **Weak** — no draft-age signal; partly covered by P0-9 |
| Receives an expired session | 401 on any call; refresh available | **Solid** |
| Has multiple devices open | State-machine guards reject illegal transitions; last legal write wins | **Acceptable** — no optimistic concurrency token, but every dangerous transition is guarded |
| Two users change the same record | Approvals serialise via `current_step_sequence`; allocation via row locks | **Solid** |
| Two orders race for the last unit | `SELECT FOR UPDATE` in deterministic order + CHECK constraint | **Solid** — tested under `-m concurrency` |
| Attempts malicious input | Pydantic `extra="forbid"`, typed UUIDs, ORM parameter binding, DB CHECKs | **Solid** |
| Brute-forces login | **No rate limiting** | **Weak** — see [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) |
| Needs an audit trail | Append-only, actor-attributed, monotonically ordered | **Solid** — exceeds requirement |
| Needs to recover from failure | Typed errors carry actionable `details`; transactions are atomic | **Solid** |
| Lists 10,000 deals | Unbounded query with a per-deal N+1 | **Weak** — P0-3 |
| Filters a report by rep and period | No such endpoint | **Missing** — P0-1 |
| Reduces a subscription mid-term | No endpoint | **Missing** — P0-5 |
| Cancels a subscription | No endpoint | **Missing** — P0-6 |

---

## Execution sequence

Dependency-ordered, because some items unblock others.

1. **P0-3 pagination and `Page[T]`** — establishes the list contract before other list endpoints are written
2. **P0-2 quote list** — built on that contract
3. **P0-9 per-tenant settings** — P0-4 and B9.1 both need configurable thresholds
4. **P0-7 order-level discount** — touches `CommercialEngine` and `PolicyEngine`; do it before anything else reads totals
5. **P0-4 discount anomaly** — needs settings (3) and feeds reporting (7)
6. **P0-8 delivery promise and slippage**
7. **P0-1 reporting module** — consumes the filter conventions from (1) and the anomaly data from (5)
8. **P0-5 subscription change** — then **P0-6 cancellation and credit notes**, which extends it
9. **P1 batch** — variants, price lists, promoted products, dismiss, CRUD holes, dependency-declared authorization
10. **P2 batch** — what-if simulation first; it is the highest demo value per line of code

Detail in [`BACKEND_IMPLEMENTATION_PLAN.md`](./BACKEND_IMPLEMENTATION_PLAN.md).

---

## Resolution

### P0 — all nine closed

| ID | Gap | Delivered |
|---|---|---|
| P0-1 | Reporting module absent | `app/services/reporting_service.py`, `export_service.py`, `routers/reports.py`. Six reports, all four PDF A7 filters, `sales_teams` + membership, CSV/XLSX/PDF export |
| P0-2 | No quote list | `GET /quotes` with 22 card fields, 9 filters, search, sorting |
| P0-3 | No pagination | `app/schemas/query.py`; `Page[T]` adopted on 6 routes; `list_deals` N+1 replaced with two bulk queries |
| P0-4 | No discount anomaly | `app/services/anomaly_service.py` — per-rep mean/stdev baseline, configurable sigma and minimum sample, `DISCOUNT_ANOMALY` attention type, `GET /reports/discount-anomalies` |
| P0-5 | Proration preview-only | `POST /billing/subscriptions/{id}/change` — blended current period, future periods regenerated, invoiced periods refused |
| P0-6 | No cancellation or credit notes | `credit_notes` table, cancel endpoint, refund and void, `PaymentStatus.REFUNDED` now reachable |
| P0-7 | No order-level discount | Compounds with the line tier; **the compounded figure is what policy ceilings evaluate**, closing the PDF §10 loophole |
| P0-8 | No delivery promise | `promised_delivery_date` on order and line, `POST .../deliver`, slippage signal, `overdue_delivery` filter |
| P0-9 | Thresholds not per-tenant; no nudge | `organization_settings` + `GET/PATCH /admin/settings`; acknowledge, nudge and escalate endpoints |

### P1 — all eleven closed

Variants now attach to quote lines and apply `price_delta`/`cost_delta`; tier
price lists resolve during line pricing; `products.is_promoted` drives ranking
and the B5 promotion tag; dismissals persist per version; warehouse GET/PATCH
added; `POST /quotes/{id}/lose` and `POST /orders/{id}/cancel` make previously
unreachable statuses reachable; invoice void plus computed `is_overdue`;
inline role checks in `orders.py` and `billing.py` replaced with declared
`OpsUser` / `AllocatingUser` / `FinanceUser` dependencies so restrictions
appear in the OpenAPI schema; attention-item ownership enforced.

Deal-stage transition validation (P1-9) remains open and is documented below.

### P2 — two of seven delivered

**P2-1 what-if simulation** — `POST /quote-versions/{id}/simulate`. Returns a
baseline and a proposal with full risk decomposition, deltas, the approval
levels a change would add or remove, and a display-ready `verdict`. A test
asserts the prediction equals a real submit **exactly**, and another asserts
nothing is persisted.

**P2-5 payment-terms policy seeded** — the `PAYMENT_TERMS_LIMIT` evaluator was
fully built and never fired because nothing seeded a policy of that type.

Not done: P2-2 co-purchase mining, P2-3 deal replay, P2-4 reorder alerts,
P2-6 approval SLA surfacing, P2-7 recommendation margin floor is wired to
settings but has no dedicated endpoint.

### Security — five of five pre-frontend items closed

`.env.example` added and `.env` git-ignored; startup validators refuse the
placeholder JWT secret, wildcard CORS and `debug=True` outside development;
CORS pinned with credentials off and methods narrowed; auth rate limiting with
429 + `Retry-After`; attention-item ownership enforced.

### Still open, deliberately

| Item | Priority | Rationale |
|---|---|---|
| Refresh-token revocation | P2 | Stateless by design; deactivation already breaks refresh immediately |
| `ADMIN` step override | P2 | Break-glass, fully audited; a separate role is the right fix, not a quick one |
| Co-purchase recommendation mining | P2 | A6 is optional in the PDF; the rule-based engine is explainable |
| Deal replay endpoint | P2 | The data exists; assembly is a nice-to-have |
| Deal-stage transition validation | P1 | Data-integrity, not security |
| Idempotency-key pruning | P3 | Slow growth only |
| Unused schema cleanup | P3 | Harmless |
| Variant-level inventory | P2 | `inventory` is unique on `(warehouse, product)`; documented limitation |
| Multi-currency FX | REJECT | PDF §7 calls it a bonus |

### Test suite performance

Not a PDF requirement, but it was blocking iteration. Two fixes took the suite
from a projected ~45 minutes to **6.6 minutes**:

- The engine forced `NullPool` under test, costing a full TCP connect and auth handshake **per statement** — 133 ms/query measured versus 4.8 ms pooled. Pinning `asyncio_default_test_loop_scope = session` removed the cross-loop hazard the workaround existed for.
- The per-test fixture truncated all 38 tables unconditionally; `TRUNCATE` benchmarked at a flat ~2.7s regardless of table count because it rewrites relation files and syncs the data directory. It now detects dirty tables in one query and uses `DELETE` with foreign-key triggers suspended.

`test_auth.py` (18 tests): 101.4s → 16.2s.
