# DealFlow360 Backend Progress

> **COMPLETED: 96 / 96 tasks (100%)**
> **P0 verified end-to-end. 344 automated tests passing against real PostgreSQL.**

```
==================================================
DEALFLOW360 BACKEND BUILD — COMPLETE
Phase: 11/11
Progress: 96/96 tasks (100%)
Tests:   344 passed / 0 failed
Suite:   ~4 min against PostgreSQL 16 (mydb_test)
==================================================
```

| Verification | Result |
|---|---|
| PostgreSQL 16 on :5433 (Docker) | ✅ healthy |
| `alembic upgrade head` from an empty database | ✅ 2 revisions |
| `alembic check` (no model/schema drift) | ✅ clean |
| All 33 tables · 112 FKs · 205 indexes · 645 constraints | ✅ verified |
| 95 NUMERIC columns · 0 float columns | ✅ verified |
| 0 naive timestamps | ✅ verified |
| Seed run twice | ✅ 32 rows, then 0 |
| FastAPI boot · `/health` · `/docs` · `/openapi.json` | ✅ 68 paths, 131 schemas |
| End-to-end canonical flow | ✅ passing |
| Final self-audit (20 dangerous questions) | ✅ all safe |

---

## Phase 1 — Foundation (8/8)
- [x] Inspect repository / environment
- [x] Project scaffold + directory layout
- [x] Virtual environment (Python 3.13)
- [x] Dependencies (`requirements.txt`)
- [x] Docker PostgreSQL on port 5433 (`docker-compose.yml`)
- [x] Test database `mydb_test` provisioned
- [x] `.env.example` + `.gitignore`
- [x] `PROGRESS.md` checklist

## Phase 2 — Application Core (6/6)
- [x] `app/config.py` env-based settings (rejects non-asyncpg URLs)
- [x] `app/db.py` async engine + session factory
- [x] `app/errors.py` consistent API error taxonomy
- [x] `app/main.py` app factory + CORS + health endpoint
- [x] `app/events.py` in-process domain event bus
- [x] FastAPI starts, `/health` + `/docs` respond

## Phase 3 — Database, 33 tables (14/14)
- [x] `models/base.py` (UUID PK, tz-aware timestamps, money types)
- [x] Identity models — organizations, roles, users, contacts
- [x] Commercial models — customer_profiles, products, product_variants, price_lists, deals
- [x] Quote models — quotes, quote_versions, quote_lines
- [x] Decision Fabric models — policies, policy_results, commercial_snapshots
- [x] Approval models — approval_requests, approval_steps, approval_decisions
- [x] Decision tracking models — decision_impacts, attention_items
- [x] Negotiation models — negotiation_threads, negotiation_messages
- [x] Execution models — sales_orders, sales_order_lines, fulfillments
- [x] Inventory models — warehouses, inventory, inventory_allocations
- [x] Billing models — billing_schedules, invoices, payments
- [x] System models — audit_events, idempotency_keys
- [x] Alembic init + migrations (2 revisions, async env)
- [x] Verified: 33 tables, FKs, constraints, partial unique indexes

## Phase 4 — Auth, RBAC, Tenancy (8/8)
- [x] Password hashing + JWT access/refresh tokens (typed)
- [x] `POST /auth/signup`
- [x] `POST /auth/login`
- [x] `POST /auth/refresh`
- [x] `GET /users/me`
- [x] `get_db` / `get_current_user` / `require_role` dependencies
- [x] Tenant isolation (404 not 403 on cross-tenant)
- [x] Auth (18) + RBAC (51) + tenancy (20) tests pass

## Phase 5 — Commercial Core (10/10)
- [x] Admin products CRUD + `GET /products`
- [x] Admin warehouses CRUD + `GET /warehouses`
- [x] Admin policies CRUD + `GET /policies`
- [x] `POST /admin/seed` + `scripts/seed.py` (deterministic, idempotent)
- [x] Customers (`customer_profiles`) + contacts endpoints
- [x] Deals (`POST /deals`, `GET /deals/{id}`)
- [x] Quotes (`POST /deals/{id}/quotes`, `GET /quotes/{id}`)
- [x] Quote lines add/patch/delete (DRAFT only)
- [x] `CommercialEngine` + `POST /quote-versions/{id}/calculate` + snapshots
- [x] Commercial engine tests pass (24) — exact Decimal, hand-verified totals

## Phase 6 — Policy Engine + Decision Fabric (9/9)
- [x] Category discount ceilings per tier (per-line, most-specific match wins)
- [x] Minimum margin rule
- [x] Discount signing-authority rule (amount-based routing)
- [x] Deterministic blended risk algorithm (documented + hand-verified)
- [x] Explainability on every policy result
- [x] `GET /quote-versions/{id}/policy-results`
- [x] `DecisionFabric` material-change detection (provenance-based line matching)
- [x] `GET /quote-versions/{id}/impact` (pure read)
- [x] Policy (33) + Decision Fabric (17) tests pass

## Phase 7 — Approvals + Staleness (9/9)
- [x] `POST /quote-versions/{id}/submit` (auto-routes, no manual request step)
- [x] Approval routing from real policy evaluation
- [x] Ordered steps (SALES_MANAGER → FINANCE)
- [x] `GET /approvals/inbox`, `GET /approvals/{id}`
- [x] approve / reject / request-revision
- [x] Sales cannot approve; nobody approves their own quote
- [x] Quote versioning immutability (all 21 state × operation combinations)
- [x] Approval staleness on material revision (+ auto-approval recorded)
- [x] Approval (17) + versioning (39) tests pass

## Phase 8 — Negotiation + Portal (7/7)
- [x] `POST /quote-versions/{id}/revisions`
- [x] `GET /portal/quotes` + `GET /portal/quotes/{id}` (redacted by type)
- [x] Portal messages GET/POST + seller reply
- [x] Counter-offer triggers revision + Decision Fabric
- [x] Customer never receives cost/margin/risk (asserted in OpenAPI too)
- [x] Confirmation blocked while approval is stale
- [x] Negotiation tests pass (16)

## Phase 9 — Orders, Inventory, Billing (11/11)
- [x] `POST /portal/quotes/{id}/confirm` (atomic order creation)
- [x] Idempotency keys protect confirmation
- [x] `GET /orders/{id}`
- [x] `InventoryService` atomic allocation with `SELECT FOR UPDATE`
- [x] `POST /orders/{id}/allocate` (generic multi-warehouse split)
- [x] Backorder / shortage handling + restock consolidation
- [x] `POST /orders/{id}/fulfill` (one shipment per warehouse)
- [x] `BillingService` one-time + recurring schedules
- [x] Proration service + preview endpoint
- [x] `GET /billing/schedules`
- [x] Inventory (20) + billing (23) + idempotency (9) tests pass

## Phase 10 — Control Tower, Audit, E2E (9/9)
- [x] `AuditService` append-only events via a global subscriber
- [x] Attention item engine (6 types, 4 severities, deduped)
- [x] `GET /dashboard/control-tower`
- [x] `GET /dashboard/attention-items` + manual resolve
- [x] `GET /dashboard/deal-health` (deterministic penalty model)
- [x] Audit tests pass (14)
- [x] Dashboard tests pass (19)
- [x] **End-to-end canonical flow test passes**
- [x] Full pytest suite green (344)

## Phase 11 — Verification + Docs (5/5)
- [x] `scripts/verify_db.py` — 33 tables, FKs, constraints, indexes, no floats
- [x] Seed idempotency verified (run twice)
- [x] `/docs` + `/openapi.json` verified on a live server
- [x] README complete (25 sections + blended risk formula + 3 appendices)
- [x] `scripts/self_audit.py` — 20 dangerous questions, all answered safely

---

## Bugs found and fixed during the build

Each was found by a test, root-caused, fixed at the source, and is now covered
by a regression test.

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `MissingGreenlet` reading a version after `/calculate` | SQL-expression `onupdate` on `updated_at` forces a post-fetch that leaves the attribute expired; the next plain read attempts sync IO on an AsyncSession | Python-side `onupdate` (`app/models/base.py`) |
| 2 | `GET /policy-results` returned an empty list | Policy evaluation only ran on submit, not on line edits, so the stored results lagged the totals | `QuoteService.recalculate()` runs both engines; every line-mutation path goes through it |
| 3 | Snapshot held a stale risk score | The snapshot is written before risk is known | `PolicyEngine.evaluate_and_persist` back-fills the current snapshot |
| 4 | add+remove reported as one product swap | Lines were matched across versions by `line_number` | `quote_lines.source_line_id` provenance link (migration `26bdcb29`) |
| 5 | Spurious `required_approvals` change on every first revision | `[]` conflated "never submitted" with "needs nobody" | `required_levels_for_version` returns `None` when no request exists |
| 6 | Auto-approved quotes had no decision to mark stale | Auto-approval wrote no `approval_requests` row | `ApprovalService.record_auto_approval` |
| 7 | `superseded_by_request_id` always null | The stale ids were never passed to `open_request` | Threaded through from `DecisionFabric` |
| 8 | Impact read lost the "customer counter" narrative | The read path had no trigger context | Derived from `quote_versions.source` |
| 9 | Quantities rendered as `60.0000` in operator prose | No shared quantity formatter | `format_quantity()` in `commercial_engine` |
| 10 | Losing concurrent confirm raised `InvalidRequestError` | `expunge` called on an object the savepoint rollback had already evicted | `discard_pending()` helper |
| 11 | Losing concurrent confirm then raised `PendingRollbackError` | `session.add()` was *outside* `begin_nested()`, so the pending INSERT survived the savepoint rollback | Moved `add()` inside the savepoint in all 4 places |
| 12 | Superseded versions left CRITICAL alerts open | Nothing retired a replaced version's attention items | `create_revision` resolves them |
| 13 | Suite failed only in full-run order | Test asserted `lines[0]` was the laptop; allocation orders lines by `product_id` for deterministic locking | Test selects by product name |

## Commands

```bash
docker compose up -d                                  # PostgreSQL :5433
alembic upgrade head                                  # migrate
python -m scripts.verify_db                           # verify the schema
python -m scripts.seed                                # seed (idempotent)
uvicorn app.main:app --reload                         # run
ENVIRONMENT=test pytest                               # 344 tests
ENVIRONMENT=test pytest tests/test_end_to_end.py -s   # canonical flow, narrated
ENVIRONMENT=test python -m scripts.self_audit         # 20 safety questions
```
