# DealFlow360 — Backend

> An intelligent, self-governing sales operations platform.
> **The backend is the source of truth.** It calculates and persists every
> authoritative value; the client renders them.

FastAPI · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · PostgreSQL 16 · JWT

**Status:** Complete against the hackathon problem statement — **433 automated
tests passing** against real PostgreSQL, including the full canonical flow end
to end. 38 tables, 117 API operations.

> **Full documentation lives in [`docs/`](docs/)** — 15 documents covering the
> problem analysis, user ecosystem, journeys, architecture, data model, entity
> lifecycles, requirement traceability, gap analysis, security audit, judge
> strategy, API reference written from captured live payloads, and a frontend
> integration guide. Start with
> [`docs/REQUIREMENT_TRACEABILITY_MATRIX.md`](docs/REQUIREMENT_TRACEABILITY_MATRIX.md)
> for coverage against the PDF, or
> [`docs/FRONTEND_INTEGRATION_GUIDE.md`](docs/FRONTEND_INTEGRATION_GUIDE.md) to
> build a client.

### What was added after the initial P0 build

| PDF module | Addition |
|---|---|
| **A7** Reporting | Six reports with Period / Team / Rep / Approval-Status / Product filters, plus CSV, XLSX and PDF export. `sales_teams` entity added so the Team filter has a subject |
| **A5 / B7** Subscription lifecycle | Mid-cycle quantity and interval changes with real proration, cancellation, and `credit_notes` with partial refunds |
| **B9** Deal health | Discount anomaly against each rep's own historical average, delivery-promise slippage, and acknowledge / nudge / escalate actions |
| **B3** Quote builder | Order-level discount that compounds with the line tier — and is evaluated by policy, so it cannot bypass a per-line ceiling |
| **B1 / B2** Lists | `GET /quotes` for the Quotations list and Kanban, plus `Page[T]` pagination, filtering and sorting across every list |
| **A2** Catalog | Product variants now attach to quote lines and apply price/cost deltas; tier price lists resolve during pricing. Both were previously inert |
| **A3 / B9** Configuration | `organization_settings` makes the approval-escalation threshold, risk weights, stalled-deal window and anomaly sensitivity per-tenant |
| **A6 / B5** Upsell | Promoted products with a promotion tag, and dismissals that persist |
| Differentiator | `POST /quote-versions/{id}/simulate` — score a hypothetical discount, see which approvers it would add, persist nothing |
| Security | Auth rate limiting, pinned CORS, startup validators refusing the demo posture in production, enforced attention-item ownership |

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Technology stack](#3-technology-stack)
4. [Setup](#4-setup)
5. [PostgreSQL via Docker](#5-postgresql-via-docker)
6. [Environment variables](#6-environment-variables)
7. [Database migrations](#7-database-migrations)
8. [Seed data](#8-seed-data)
9. [Running the backend](#9-running-the-backend)
10. [Running the tests](#10-running-the-tests)
11. [API documentation](#11-api-documentation)
12. [Authentication](#12-authentication)
13. [Roles](#13-roles)
14. [Business rules and invariants](#14-business-rules-and-invariants)
15. [Discount engine (CommercialEngine)](#15-discount-engine-commercialengine)
16. [Blended risk algorithm](#16-blended-risk-algorithm)
17. [Decision Fabric](#17-decision-fabric)
18. [Quote versioning](#18-quote-versioning)
19. [Approval staleness](#19-approval-staleness)
20. [Inventory allocation](#20-inventory-allocation)
21. [Billing](#21-billing)
22. [Audit system](#22-audit-system)
23. [Canonical demo flow](#23-canonical-demo-flow)
24. [Known limitations](#24-known-limitations)
25. [P1 future work](#25-p1-future-work)

Appendix: [Architecture decisions](#appendix-a--architecture-decisions) ·
[Error codes](#appendix-b--error-codes) · [Endpoint map](#appendix-c--endpoint-map)

---

## 1. Project overview

DealFlow360 governs the whole commercial lifecycle of a B2B deal — quote,
discount approval, customer negotiation, order, fulfilment and billing — and
keeps the governance honest as the deal changes underneath it.

The problem it solves is the one every CPQ system gets wrong: a quote is
approved, the customer then asks for something different, and the approval that
was granted against the *old* numbers silently continues to authorise the *new*
ones. DealFlow360 detects that, invalidates the stale decision, re-routes
approval, and blocks the order until a human signs off on what is actually
being sold.

What makes it "self-governing":

| Capability | Meaning |
|---|---|
| **Per-line policy evaluation** | A 12% discount can pass on hardware and breach on services in the same quote. |
| **Explainable decisions** | Every policy result carries prose, the actual value, the threshold and the overage. Never a bare score. |
| **Blended risk** | One deterministic, documented, revenue-weighted score across all breaches. |
| **Material change detection** | Field-level diff between quote versions, with a materiality judgement per field. |
| **Approval staleness** | A material change invalidates prior decisions and blocks confirmation. |
| **Control Tower** | An action queue where each item states why, impact, owner and next action. |
| **Full audit trail** | Append-only, actor-attributed, ordered — every transition, no exceptions. |

## 2. Architecture

```
                    ┌──────────────────────────────────┐
   HTTP ───────────►│  routers/     validate, delegate │
                    │               own the commit     │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │  services/    all business logic │
                    │                                  │
                    │  CommercialEngine  → money       │
                    │  PolicyEngine      → governance  │
                    │  DecisionFabric    → change+impact│
                    │  ApprovalService   → routing     │
                    │  NegotiationService→ portal      │
                    │  InventoryService  → allocation  │
                    │  BillingService    → schedules   │
                    │  OrderService      → confirmation│
                    │  AuditService      → trail       │
                    │  DashboardService  → Control Tower│
                    └───────────────┬──────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
      ┌───────▼──────┐    ┌─────────▼────────┐   ┌────────▼───────┐
      │ models/  33  │    │ events.py        │   │ middleware/    │
      │ tables       │    │ in-process bus   │   │ auth · tenant  │
      └───────┬──────┘    └─────────┬────────┘   └────────────────┘
              │                     │
              │        every event writes an audit row
              │        inside the caller's transaction
              │
      ┌───────▼────────────────────────────────────────────┐
      │  PostgreSQL 16 — NUMERIC money, JSONB, partial     │
      │  unique indexes, CHECK constraints, FOR UPDATE     │
      └────────────────────────────────────────────────────┘
```

**Layering rules**

- Routers never contain business rules. They validate input, call one service,
  and own the `commit()`. That makes the transaction boundary visible in one
  place per endpoint.
- Services never return HTTP concerns; they raise typed errors from
  `app/errors.py` which map to a single JSON envelope.
- The database is the last line of defence. Where an invariant can be expressed
  as a constraint, it is — so an application bug produces a failed transaction
  rather than corrupt commercial data.

**Domain events.** `app/events.py` is a synchronous in-process bus (no Kafka, no
broker). Handlers run on the *caller's* session, so an audit record and the
state change it describes commit or roll back together. A global subscriber
turns every emitted event into an `audit_events` row, which is why no service
can forget to log.

## 3. Technology stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 (3.11+ supported) |
| Web | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (async, `asyncpg`) |
| Validation | Pydantic v2 + pydantic-settings |
| Migrations | Alembic 1.14 (async env) |
| Database | PostgreSQL 16 |
| Auth | python-jose (JWT), passlib + bcrypt |
| Tests | pytest, pytest-asyncio, httpx `ASGITransport` |

## 4. Setup

```bash
git clone <repo> && cd DealFlow360

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit JWT_SECRET_KEY
```

## 5. PostgreSQL via Docker

Compose publishes PostgreSQL on **5433** to avoid clashing with a local
install, and creates the integration-test database on first boot.

```bash
docker compose up -d
docker compose ps             # wait for "healthy"
```

This gives you:

- `mydb` — the application database
- `mydb_test` — used by the pytest suite (created by
  `scripts/init_test_db.sql`)

Connection string: `postgresql://postgres:mysecretpassword@localhost:5433/mydb`

Credentials live only in `.env` / `docker-compose.yml`; no Python module
contains a password. `app/config.py` rejects any `DATABASE_URL` that is not
`postgresql+asyncpg://`, so the app cannot be started against SQLite by
accident.

## 6. Environment variables

Full list in [`.env.example`](.env.example). The ones that matter:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…5433/mydb` | Application database |
| `TEST_DATABASE_URL` | `…5433/mydb_test` | Used when `ENVIRONMENT=test` |
| `ENVIRONMENT` | `development` | `test` switches to the test DB + NullPool |
| `JWT_SECRET_KEY` | dev placeholder | **Replace.** `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `BCRYPT_ROUNDS` | `12` | Password KDF work factor |
| `DEFAULT_TAX_RATE_PCT` | `0.0` | Fallback when neither product nor customer sets one |
| `RISK_DISCOUNT_OVERAGE_WEIGHT` | `3.0` | Blended risk — see §16 |
| `RISK_BREADTH_WEIGHT` | `5.0` | Blended risk — see §16 |
| `RISK_MARGIN_WEIGHT` | `5.0` | Blended risk — see §16 |
| `RISK_DEPTH_WEIGHT` | `0.4` | Blended risk — see §16 |
| `RISK_FINANCE_ESCALATION_THRESHOLD` | `60.0` | Score at which Finance is pulled in |
| `SEED_DEFAULT_PASSWORD` | `Password123!` | Demo-only seed password |

## 7. Database migrations

```bash
alembic upgrade head          # apply
alembic check                 # assert models match the schema
alembic downgrade -1          # roll back one revision
alembic revision --autogenerate -m "description"
```

Alembic reads the URL from `app.config`, so migrations and the app can never
disagree about which database they mean.

**Verification script** — asserts the 38 tables, foreign keys, the business
constraints, the partial unique indexes, that no column is floating point, and
that no timestamp is naive:

```bash
python -m scripts.verify_db
```

```
[tables]   expected 33, found 33
  ✓ all 33 business tables present
[fks]      112 foreign keys across 31 tables
[constraints] 645 total; checking business invariants
  ✓ sales_orders.uq_sales_orders_quote_version_id — one order per quote version
  ✓ inventory.ck_inventory_no_over_reservation — inventory cannot over-reserve
  …
[indexes]  205 total; checking partial unique indexes
  ✓ approval_requests.uq_approval_requests_one_pending_per_version
  ✓ attention_items.uq_attention_items_live_per_source
[money]    ✓ zero float/double columns — all money is NUMERIC (95 columns)
[time]     ✓ all timestamps are timezone-aware
VERIFICATION PASSED
```

### The 38 tables

| Group | Tables |
|---|---|
| Identity (4) | `organizations` `roles` `users` `contacts` |
| Commercial (5) | `customer_profiles` `products` `product_variants` `price_lists` `deals` |
| Quotes (3) | `quotes` `quote_versions` `quote_lines` |
| Decision Fabric (3) | `policies` `policy_results` `commercial_snapshots` |
| Approvals (3) | `approval_requests` `approval_steps` `approval_decisions` |
| Decision tracking (2) | `decision_impacts` `attention_items` |
| Negotiation (2) | `negotiation_threads` `negotiation_messages` |
| Execution (3) | `sales_orders` `sales_order_lines` `fulfillments` |
| Inventory (3) | `warehouses` `inventory` `inventory_allocations` |
| Billing (3) | `billing_schedules` `invoices` `payments` |
| System (2) | `audit_events` `idempotency_keys` |

## 8. Seed data

```bash
python -m scripts.seed        # or POST /admin/seed as an ADMIN
python -m scripts.seed        # run again: creates nothing
```

Deterministic, idempotent (every entity looked up by natural key) and
transactional. Re-running never disturbs live inventory reservations.

**Organizations** — TechSupply Solutions (seller) · Acme Corporation (buyer,
**GOLD**, **NET 30**, 500,000 credit limit)

**Users** — all with password `Password123!` *(demo only)*

| Email | Role |
|---|---|
| `sales@techsupply.com` | SALES |
| `manager@techsupply.com` | MANAGER |
| `finance@techsupply.com` | FINANCE |
| `ops@techsupply.com` | OPS |
| `admin@techsupply.com` | ADMIN |
| `customer@acme.com` | CUSTOMER (Acme) |

**Products**

| SKU | Product | Category | List | Cost | Billing |
|---|---|---|---|---|---|
| `HW-LAPTOP-01` | Business Laptop | Hardware | 1,200 | 800 | one-time, stock-tracked |
| `HW-MONITOR-27` | 27" Monitor | Hardware | 400 | 200 | one-time, stock-tracked |
| `SV-INSTALL-01` | Installation Service | Service | 500 | 150 | one-time |
| `SB-SUPPORT-01` | Annual Support Plan | Subscription | 300/yr | 50 | recurring, yearly |

**Warehouses** — Main Warehouse (priority 10, ship 120): 60 laptops, 150
monitors · East Depot (priority 20, ship 180): 40 laptops, 50 monitors

**Policies**

| Code | Rule | Threshold | On breach |
|---|---|---|---|
| `GOLD-HW-CEILING` | Gold + Hardware discount | ≤ 15% | Sales Manager |
| `GOLD-SV-CEILING` | Gold + Service discount | ≤ 10% | Sales Manager |
| `GOLD-SB-CEILING` | Gold + Subscription discount | ≤ 10% | Sales Manager |
| `STD-HW-CEILING` | Any tier + Hardware (fallback) | ≤ 10% | Sales Manager |
| `MIN-MARGIN-10` | Blended margin floor | ≥ 10% | Finance |
| `DISCOUNT-AUTHORITY-20K` | Total discount signing authority | ≤ 20,000 | Finance |

## 9. Running the backend

```bash
uvicorn app.main:app --reload --port 8000
curl localhost:8000/health
```

```json
{"status":"ok","app":"DealFlow360","version":"1.0.0",
 "database":"up","event_handlers":{"*":1}}
```

## 10. Running the tests

The suite runs against **real PostgreSQL**. There is no SQLite fallback: the
schema depends on JSONB, partial unique indexes, `SELECT … FOR UPDATE` and
NUMERIC semantics, so testing on another engine would verify something we do
not ship.

```bash
ENVIRONMENT=test pytest                    # all 344
ENVIRONMENT=test pytest tests/test_end_to_end.py -s   # the canonical flow, narrated
ENVIRONMENT=test pytest -m concurrency     # row-locking tests only
```

| File | Tests | Covers |
|---|---:|---|
| `test_auth.py` | 18 | signup, login, JWT, refresh, token-type confusion |
| `test_models.py` | 22 | 38 tables, no floats, tz-aware, DB constraints |
| `test_commercial_engine.py` | 24 | Decimal arithmetic, totals, margin, snapshots |
| `test_policy_engine.py` | 33 | ceilings, margin floor, blended risk, explainability |
| `test_quote_versioning.py` | 39 | the full immutability matrix, revisions |
| `test_decision_fabric.py` | 17 | material change, staleness, causal chain |
| `test_approval_flow.py` | 17 | routing, ordered steps, self-approval ban |
| `test_rbac.py` | 51 | every role × every restricted endpoint |
| `test_tenant_isolation.py` | 20 | two tenants, zero leakage |
| `test_negotiation.py` | 16 | portal redaction, counter-offers, blocking |
| `test_inventory.py` | 20 | 60/40 split, backorder, **concurrency** |
| `test_billing.py` | 23 | one-time + recurring, intervals, proration |
| `test_idempotency.py` | 9 | duplicate confirm/allocate, **concurrency** |
| `test_audit.py` | 14 | trail completeness, actor attribution, no floats |
| `test_dashboard.py` | 19 | Control Tower, deal health |
| `test_end_to_end.py` | 2 | **the canonical P0 flow** |

Each test starts from a truncated database, so ordering never matters. Under
`ENVIRONMENT=test` the engine uses `NullPool` (asyncpg connections are bound to
their creating event loop) and bcrypt drops to 4 rounds — the hashing code path
is identical, and the setting is unreachable outside tests.

## 11. API documentation

- Swagger UI — <http://localhost:8000/docs>
- ReDoc — <http://localhost:8000/redoc>
- OpenAPI — <http://localhost:8000/openapi.json> (68 paths, 131 schemas)

**Every** non-2xx response uses one envelope, so a client can branch on a
stable `code` instead of parsing prose:

```json
{
  "error": {
    "code": "STALE_APPROVAL",
    "message": "Approval of version 1 is no longer valid: Discount on 'Business Laptop' increased from 18% to 25% …",
    "details": { "quote_version_id": "…", "version_number": 2 }
  }
}
```

**Money crosses the wire as a JSON string** (`"132710.00"`), not a number. A
JSON number would be parsed as an IEEE-754 double by any JavaScript client and
quietly lose cents.

## 12. Authentication

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"sales@techsupply.com","password":"Password123!"}' \
  | jq -r .tokens.access_token)

curl localhost:8000/users/me -H "Authorization: Bearer $TOKEN"
```

| Endpoint | Purpose |
|---|---|
| `POST /auth/signup` | Create a user, optionally its organization |
| `POST /auth/login` | Credentials → access + refresh token |
| `POST /auth/refresh` | Refresh token → new pair |
| `GET /users/me` | The authenticated principal |

Access tokens carry `sub`, `type`, `org`, `role`, `email`, `iat`, `exp`, `jti`.
The embedded role is **observability only** — every request re-reads the user
row, so deactivating a user or changing their role takes effect immediately
rather than at token expiry (both behaviours are tested). Tokens are typed:
a refresh token presented as a bearer token is rejected with
`WRONG_TOKEN_TYPE`.

## 13. Roles

| Role | Can | Cannot |
|---|---|---|
| `SALES` | Author deals, quotes, lines; submit; send; revise; allocate | Approve anything |
| `MANAGER` | Everything SALES can, plus approve `SALES_MANAGER` steps | Approve a quote **they** authored |
| `FINANCE` | Approve `FINANCE` steps; issue invoices; record payments | Author deals |
| `OPS` | Allocate and fulfil orders | Author deals; approve |
| `ADMIN` | Configure catalog/warehouses/policies; act on any step; seed | Approve their own quote |
| `CUSTOMER` | `/portal/*` only, scoped to their own organization | Every internal endpoint |

MANAGER can author deals on purpose — sales managers own deals in practice.
What stops them waving their own quote through is the self-approval check, not
the absence of authoring rights: **authorship, not role, disqualifies an
approver.**

## 14. Business rules and invariants

Every item below is enforced in code *and* covered by a named test.

**Authority**
1. The backend calculates every total, discount, tax, cost, margin and risk
   score. No client-supplied figure is ever persisted.
2. `unit_cost` is copied from the catalog at line creation — a client cannot
   send it (`extra="forbid"`).
3. No client can approve anything; approval endpoints are role-gated *and*
   service-gated.
4. A user cannot approve a quote they created or submitted.
5. A step that already carries a decision cannot be decided again.
6. Approval routing derives from the `required_action` of the policy rows that
   actually fire, plus one documented risk-escalation rule.

**Immutability**
7. Only `DRAFT` versions accept in-place line edits.
8. `CONFIRMED` / `REJECTED` / `SUPERSEDED` are immutable forever — not even
   revisable.
9. A revision creates the next version and supersedes its parent, atomically.

**Governance**
10. The Decision Fabric runs on every revision, with no exceptions.
11. A material change invalidates prior approvals; the old decision is marked
    `STALE`, never deleted.
12. A stale approval blocks confirmation.
13. Materiality is fail-closed: listed fields count as material unless they
    moved less than an explicit epsilon.

**Isolation**
14. Internal users only ever touch rows in their own organization.
15. Cross-tenant reads return **404**, never 403, so ids cannot be enumerated.
16. Portal users reach only quotes issued to their organization.
17. Portal responses have no cost/margin/risk fields *in the schema at all*.

**Money and correctness**
18. All monetary values are `Decimal` / PostgreSQL `NUMERIC`. Zero float
    columns; asserted by both a test and `verify_db`.
19. All timestamps are timezone-aware.
20. Duplicate confirmation cannot create two orders — enforced by a UNIQUE
    constraint on `sales_orders.quote_version_id`, above the idempotency layer.
21. Inventory can never be over-allocated: `SELECT FOR UPDATE` plus a CHECK
    constraint (`quantity_reserved <= quantity_on_hand`).
22. Billing derives only from `sales_order_lines`; there is no endpoint that
    creates a schedule from nothing.
23. Every major transition writes an audit event, inside the same transaction.

## 15. Discount engine (CommercialEngine)

`app/services/commercial_engine.py` is the only code that writes a financial
column.

**Line arithmetic**

```
gross_amount    = quantity × unit_list_price × recurring_periods
discount_amount = gross_amount × discount_pct / 100
net_amount      = gross_amount − discount_amount
unit_net_price  = unit_list_price × (100 − discount_pct) / 100
tax_amount      = net_amount × tax_rate_pct / 100
total_amount    = net_amount + tax_amount
line_cost       = quantity × unit_cost × recurring_periods
line_margin     = net_amount − line_cost
line_margin_pct = line_margin / net_amount × 100
```

**Version totals** are the sum of the *rounded* lines, then:

```
total_revenue          = net_revenue + tax_amount
margin                 = net_revenue − total_cost
margin_pct             = margin / net_revenue × 100
effective_discount_pct = total_discount / gross_revenue × 100
```

**Four decisions worth stating**

- **`ROUND_HALF_UP`, not banker's rounding.** Python's default is
  `ROUND_HALF_EVEN`, which finance teams do not use. Money is 2dp, unit prices
  4dp, percentages 4dp.
- **Round per line, then sum.** Summing unrounded values and rounding once
  would make the printed line items fail to add up to the printed total — worse
  than a sub-cent aggregate difference.
- **Margin excludes tax.** Tax is collected for a tax authority; it is not the
  seller's revenue. So margin is measured against `net_revenue`.
- **`recurring_periods` multiplies the line.** For a recurring product,
  `unit_list_price` is the price *per period*, so a 12 × 50/month plan is 600 of
  contract value. Discount ceilings and margin floors judge total contract
  value, which is the number that matters.

**Snapshots.** Every calculation appends a `commercial_snapshots` row (one
`is_current` per version) holding the full line detail as JSONB. That answers
"what was true when this decision was made" and lets a historical approval be
replayed exactly.

**Worked example** — the canonical demo quote:

| Line | Qty | List | Disc | Net | Cost |
|---|---:|---:|---:|---:|---:|
| Business Laptop | 100 | 1,200 | 18% | 98,400.00 | 80,000.00 |
| 27" Monitor | 100 | 400 | 16% | 33,600.00 | 20,000.00 |
| Installation Service | 1 | 500 | 18% | 410.00 | 150.00 |
| Annual Support Plan | 1 | 300 | 0% | 300.00 | 50.00 |
| | | | | **132,710.00** | **100,200.00** |

gross 160,800.00 · discount 28,090.00 · margin **32,510.00** (**24.4970%**) ·
effective discount 17.4689% · one-time 132,410.00 · recurring 300.00

## 16. Blended risk algorithm

Deterministic, unit-consistent, individually capped, and fully reproduced by
`test_blended_risk_matches_the_documented_formula`.

```
score = min(100, (C1 + C2 + C3 + C4) × tier_sensitivity)
```

### C1 — Weighted discount overage · cap 45

For every line L that breaches its category ceiling:

```
overage_L       = discount_pct_L − ceiling_L          (percentage points)
revenue_share_L = net_amount_L / net_revenue          (0…1)
weighted_L      = overage_L × revenue_share_L

C1 = min(45, Σ weighted_L × 3.0)
```

Revenue-weighting is the point. Without it, 8 points over on a \$410 service
line would outrank 3 points over on \$98,400 of hardware. This measures
**exposure**, not indignation.

### C2 — Breadth of violation · cap 15

```
C2 = min(15, count_of_violating_lines × 5.0)
```

Several lines each slightly over is a pattern of erosion, not a rounding error.
Combined exposure must move the score even when every individual overage is
small.

### C3 — Margin shortfall · cap 40

```
C3 = min(40, max(0, margin_floor_pct − actual_margin_pct) × 5.0)
```

### C4 — Cumulative discount depth · cap 15

```
C4 = min(15, effective_discount_pct × 0.4)
```

Total giveaway matters even when every line is inside its ceiling.

### Tier sensitivity

| Tier | Factor |
|---|---:|
| PLATINUM | 1.20 |
| GOLD | 1.10 |
| SILVER | 1.00 |
| BRONZE | 0.95 |

Senior tiers already receive the most generous ceilings, so breaching one is a
larger deviation from an already-concessive baseline — and those accounts
concentrate more revenue.

### Bands

| Score | Band |
|---|---|
| 0 | NONE |
| 0 < s < 15 | LOW |
| 15 ≤ s < 40 | MEDIUM |
| 40 ≤ s < 70 | HIGH |
| s ≥ 70 | CRITICAL |

Caps sum to 115, so the clamp to 100 is real rather than decorative.

### Routing

```
required = { policy.required_action : for each VIOLATED policy }
         ∪ { FINANCE : if score ≥ RISK_FINANCE_ESCALATION_THRESHOLD (60) }
```

Steps are created in escalation order (`SALES_MANAGER` → `FINANCE`); the
highest required level is the final authority.

**Amount-threshold policies contribute 0 to the score.** Signing authority is a
question of *who* must approve, not *how risky* the deal is, and mixing
currency into a percentage-point score would make the number meaningless. They
still route approvals — which is exactly how the canonical demo pulls in
Finance on a quote whose margin is perfectly healthy.

### Worked example — canonical quote, GOLD tier

```
C1: (3 × 98400/132710) + (1 × 33600/132710) + (8 × 410/132710)
      = 2.2245 + 0.2532 + 0.0247 = 2.5024 pts
      × 3.0 = 7.5072                                    →  7.5072
C2: 3 violating lines × 5.0 = 15                        → 15.0000
C3: margin 24.4970% ≥ 10% floor                         →  0.0000
C4: 17.4689% × 0.4 = 6.9876                             →  6.9876
                                              raw total = 29.4948
                                       × 1.10 (GOLD)   = 32.4443  → MEDIUM
```

Routing: `CATEGORY_DISCOUNT_CEILING` → Sales Manager;
`DISCOUNT-AUTHORITY-20K` (28,090 > 20,000) → Finance. Steps:
**SALES_MANAGER → FINANCE**.

## 17. Decision Fabric

`app/services/decision_fabric.py`. Given two versions it answers, in one
structured result:

> what changed → did it matter → which policies now fire → whose earlier
> decision is no longer valid → who must act next

`GET /quote-versions/{id}/impact` returns:

```jsonc
{
  "changes":            [ /* every diff, material or not */ ],
  "material_changes":   [ /* field, old, new, severity, reason */ ],
  "policy_results":     [ /* explainable evaluations */ ],
  "stale_decisions":    [ /* approval_request_id, previous_decision, reason */ ],
  "affected_entities":  [ /* {type, id, reason} */ ],
  "required_approvals": [ /* {type, reason, triggered_by[]} */ ],
  "attention_items":    [ /* type, severity, title, reason, impact, owner, action */ ],
  "explanation": {
    "summary": "…", "causal_chain": ["…"],
    "what_changed": "…", "why_it_matters": "…",
    "who_is_affected": "…", "what_happens_next": "…"
  },
  "has_material_change": true,
  "blocks_confirmation": true
}
```

**Material fields**

| Field | Material? | Epsilon |
|---|---|---|
| `discount_pct` | yes | > 0.01 pts |
| `quantity` | yes | any change |
| `unit_price` | yes | any change |
| `product` | yes | any change |
| `recurring_periods`, `recurring_interval` | yes | any change |
| line added / removed | yes | — |
| `payment_terms` | yes | any change |
| `margin_pct` | yes | > 0.10 pts |
| `total_revenue` | yes | > 0.10% relative |
| `effective_discount_pct` | yes | > 0.01 pts |
| `required_approvals` | yes | set changed |
| `description`, `notes` | **no** | recorded, never material |

Materiality is **fail-closed**: a governance failure should be a false positive
(an unnecessary re-approval), never a false negative (an order shipped on a
decision nobody actually made).

**Lines are matched across versions by provenance**, not position.
`quote_lines.source_line_id` links a revision's line to its parent. Matching by
`line_number` would report "line 4 removed + new line added at slot 4" as a
single innocuous product swap, hiding a real scope change from the approver.

Every diff — material or not — is persisted to `decision_impacts`, so the
impact endpoint can also say *"we looked at this and it did not matter."*

The endpoint is a **pure read**, rebuilt from `decision_impacts` +
`policy_results`; calling it repeatedly creates nothing.

## 18. Quote versioning

| State | Edit lines? | What happens instead |
|---|---|---|
| `DRAFT` | ✅ | `PATCH`/`DELETE` directly |
| `PENDING_APPROVAL` | ❌ | Create a revision |
| `APPROVED` | ❌ | Create a revision → stale check |
| `SENT` | ❌ | Create a revision → stale check |
| `NEGOTIATING` | ❌ | Create a revision → stale check |
| `CONFIRMED` | ❌ never | Immutable forever |
| `REJECTED` | ❌ never | Immutable forever |
| `SUPERSEDED` | ❌ never | Immutable forever |

Enforced in `QuoteService.assert_editable`, which the routers call *and* which
the mutation methods call — so an alternate code path cannot bypass it. All
21 state × operation combinations are tested.

**Transitions**

```
DRAFT ──submit──► PENDING_APPROVAL ──approve──► APPROVED ──send──► SENT
  ▲                      │                                          │
  └──request-revision────┘                                          │
                         │                              customer message
                      reject                                        ▼
                         ▼                                    NEGOTIATING
                     REJECTED                                       │
                                                          counter-offer
  any revisable state ──revision──► next version (DRAFT→…)          │
                    └──────────────► SUPERSEDED                     │
                                                                    ▼
                                                   confirm ──► CONFIRMED
```

`request-revision` returns the version to `DRAFT`. No approval was ever
granted, so nothing is being rewritten — it simply becomes editable again.

**Auto-approval is recorded.** A quote that violates no policy is approved on
submit, and an `approval_requests` row with `status=APPROVED` and zero steps is
written. Approval by the policy engine is still a decision: "who approved this?"
always has an answer, and a later material change has something concrete to
mark stale.

## 19. Approval staleness

The core differentiator.

```
Customer counters on the SENT version
        │
        ▼
QuoteService.create_revision  ──►  V2 created, V1 SUPERSEDED
        │
        ▼
DecisionFabric.process_version(V2, previous=V1)
        │
        ├─ CommercialEngine   → recalculate V2, snapshot
        ├─ PolicyEngine       → re-evaluate, new risk, new routing
        ├─ detect_changes(V1, V2)
        │       │
        │       ▼   material change?
        │      YES
        │       ▼
        ├─ persist decision_impacts (every diff)
        ├─ emit MATERIAL_CHANGE_DETECTED
        ├─ for each APPROVED approval_request on this quote:
        │       status → STALE   (kept, never deleted)
        │       approved steps → STALE
        │       stale_at, stale_reason recorded
        │       emit APPROVAL_MARKED_STALE
        │       raise CRITICAL attention item, owner FINANCE
        ├─ pending requests on superseded versions → CANCELLED
        ├─ open a NEW approval_request, superseded_by linked
        └─ V2.is_stale = true, V2.stale_reason = <the change>
                │
                ▼
      POST /portal/quotes/{id}/confirm  →  409 STALE_APPROVAL
                │
      Finance re-approves V2
                ▼
      V2.is_stale = false, alerts resolved, confirmation opens
```

All of this happens in **one transaction**. There is no window in which a
superseded version exists without its replacement, or a replacement exists
without its governance evaluation.

The customer sees only a safe reason — *"Your requested changes are being
reviewed by our team"* — never the margin, the policy, or who is blocking it.

## 20. Inventory allocation

`SELECT … FOR UPDATE` over every stock row for the product **before** deciding
anything, so two orders racing for the same stock serialise instead of both
reading the same availability. Rows lock in `inventory.id` order and lines
process in `product_id` order, giving every transaction identical lock ordering
and removing the deadlock window.

Belt and braces: `CHECK (quantity_reserved <= quantity_on_hand)`. Even with a
bug in this service, PostgreSQL refuses to over-allocate.

**Strategy** — nothing about 60/40 is written down anywhere:

1. If any single warehouse can cover the whole line, use it — one shipment is
   cheaper than two. Among those that can: lowest `priority`, then lowest
   shipping cost, then largest stock, then code.
2. Otherwise take the largest available stock first, minimising shipment count.
3. Whatever cannot be sourced becomes a `BACKORDERED` allocation with no
   warehouse, carrying the earliest expected restock date.

With Main = 60 and East = 40, an order for 100 falls to rule 2 and yields
**60 + 40**. `test_split_changes_when_stock_changes` rebalances to 30/70 and
asserts the split follows — the algorithm is generic, and the demo number is an
emergent property of the seed data.

Also supported: manual override (validated against real availability and the
line's outstanding quantity), partial allocation, `allow_partial=false`
all-or-nothing, backorder consolidation on restock, and one fulfilment per
warehouse. Shipping converts a reservation into an outbound movement,
decrementing both `quantity_on_hand` and `quantity_reserved`.

## 21. Billing

Every schedule traces back to a `sales_order_lines` row, and the sum of a
line's schedules equals that line's net amount **exactly** — the final period
absorbs the rounding remainder, so `SUM(amount) == line.net_amount` for any
period count. `test_split_amount_is_exact_for_any_shape` checks this for
awkward shapes like 0.05 over 4 periods.

- **One-time** lines → one `ONE_TIME` schedule, due `period_start + terms`.
- **Recurring** lines → one row *per period*, so proration, mid-term changes
  and revenue recognition are all expressible without recomputation.
- Intervals `MONTHLY` (1) / `QUARTERLY` (3) / `YEARLY` (12); periods are
  contiguous and month-end-clamped (31 Jan + 1 month = 28 Feb, or 29 in a leap
  year).
- **Proration** is a reusable service (`BillingService.prorate`), day-counted
  with both endpoints inclusive, exposed at `GET /billing/proration-preview`.

One order carries both kinds at once, which is exactly the canonical demo:
laptops + monitors + installation bill once; the Annual Support Plan recurs.

## 22. Audit system

`audit_events` is append-only — the table has **no** `updated_at` column, so
there is nothing to rewrite history with.

Each row records: `sequence` (monotonic bigint), `organization_id`,
`event_type`, `entity_type`, `entity_id`, `actor_user_id`, `actor_role`,
`actor_email`, `payload` (JSONB), `ip_address`, `occurred_at`.

`sequence` exists because a single transaction emits half a dozen events that
share the same microsecond; it gives a stable total ordering.

Events: `USER_SIGNED_UP` `USER_LOGGED_IN` `QUOTE_CREATED` `QUOTE_SUBMITTED`
`POLICY_EVALUATED` `APPROVAL_REQUESTED` `APPROVAL_GRANTED` `APPROVAL_REJECTED`
`APPROVAL_REVISION_REQUESTED` `APPROVAL_MARKED_STALE` `QUOTE_APPROVED`
`QUOTE_SENT` `CUSTOMER_COMMENTED` `CUSTOMER_COUNTERED` `QUOTE_REVISED`
`MATERIAL_CHANGE_DETECTED` `QUOTE_CONFIRMED` `ORDER_CREATED`
`INVENTORY_ALLOCATED` `INVENTORY_SHORTAGE` `ORDER_FULFILLED`
`BILLING_SCHEDULED` `ATTENTION_ITEM_CREATED` `ATTENTION_ITEM_RESOLVED`

Approval events embed `financials_at_decision`, so the record shows the numbers
the approver was actually looking at. Money in payloads is stored as **strings**
— a float round-trip through JSONB would corrupt the record of a decision, and
`test_money_in_audit_payloads_is_stored_as_strings` walks every payload to
prove none exists.

```bash
GET /audit/events?entity_type=quote_version&entity_id=…
GET /audit/quotes/{quote_id}/timeline    # the whole story, one call
```

### Control Tower

`attention_items` is an action queue, not a metric wall. Each item answers four
questions: **why** (`reason`), **impact** (`impact`), **owner**
(`owner_role`/`owner_user_id`), **what next** (`recommended_action`).

| Type | Trigger | Owner | Severity |
|---|---|---|---|
| `STALE_APPROVAL` | material change invalidated an approval | FINANCE | CRITICAL |
| `ORDER_BLOCKED` | order blocked by a stale approval | SALES | CRITICAL |
| `MARGIN_VIOLATION` | margin below the policy floor | FINANCE | HIGH |
| `INVENTORY_SHORTAGE` | allocation cannot fill the order | OPS | HIGH |
| `PENDING_APPROVAL` | quote waiting for a reviewer | MANAGER / FINANCE | MEDIUM |
| `CUSTOMER_RESPONSE_REQUIRED` | customer silent, or asked a question | SALES | MEDIUM |

Items are raised at **decision points** (submit, revision, counter) — never on
every draft recalculation, which would make the queue unreadable within
minutes. A partial unique index keeps one live item per (source, type), so
re-evaluating refreshes rather than spams. Superseding a version retires its
items: nobody can fix the margin on a version that has been replaced.

`GET /dashboard/deal-health` scores each deal deterministically from 100, with
every deduction returned as a named signal:

```
CRITICAL attention item   −30 each (cap −60)   Margin below floor  −20
HIGH attention item       −15 each (cap −30)   Stale approval      −25
MEDIUM attention item      −5 each (cap −15)   Approval pending    −10
Inventory shortage        −10                  Customer silent 14d −10
No quote yet              −10
CLOSED_WON → 100                               CLOSED_LOST → 0
```

Bands: ≥80 HEALTHY · ≥60 WATCH · ≥40 AT_RISK · <40 CRITICAL.

## 23. Canonical demo flow

Reproduced verbatim by `tests/test_end_to_end.py`. Run it narrated:

```bash
ENVIRONMENT=test pytest tests/test_end_to_end.py::test_canonical_end_to_end_flow -s
```

**Scene 1 — Build.** Sales creates a deal for Acme and a quote with 100
laptops @18%, 100 monitors @16%, 1 installation @18%, 1 annual support. The
backend computes revenue 132,710.00, cost 100,200.00, margin 32,510.00
(24.4970%). Policy evaluation flags three ceiling breaches and the 20,000
signing-authority limit; blended risk 32.44 (MEDIUM). Submit routes
**Sales Manager → Finance** automatically. v1 becomes immutable.

**Scene 2 — Approve.** Finance is refused for trying to jump the queue (403).
Manager approves, then Finance approves. Both decisions are recorded with
actor, reason, timestamp and the numbers. The quote is sent.

**Scene 3 — Portal.** The customer sees totals, discounts and line prices —
and no cost, margin, risk or policy data. Every internal endpoint returns 403.

**Scene 4 — The wow moment.** The customer counters at 25% on laptops. The
backend creates **v2** (v1 is untouched and SUPERSEDED, still reading
132,710.00). The Decision Fabric detects material changes on discount, blended
discount, margin (24.4970% → 19.3951%) and total revenue; marks the Finance
approval **STALE**; writes `decision_impacts`; raises a CRITICAL attention
item; opens a new approval request; and blocks confirmation with
`409 STALE_APPROVAL`. The customer is told only that their changes are under
review.

**Scene 5 — Confirm and execute.** Manager and Finance re-approve v2. The
customer confirms with an `Idempotency-Key`; a retry replays the same order and
exactly one order exists. Allocation splits **60 from Main Warehouse, 40 from
East Depot** across 2 shipments; laptop availability is exactly zero. Billing
produces 3 one-time schedules (124,010.00) plus 1 yearly recurring schedule
(300.00). The order fulfils in 2 shipments. The audit timeline holds 22 ordered,
actor-attributed events; the Control Tower returns to clear; deal health is
100/100 CLOSED_WON.

## 24. Known limitations

Honest list of what is *not* production-ready:

1. **Refresh tokens are stateless.** There is no revocation list, so a stolen
   refresh token stays valid until it expires. Real deployments need a
   persisted token store or short-lived rotation.
2. **Variant-level inventory is not modelled.** `inventory` is unique on
   `(warehouse_id, product_id)`; `product_variant_id` exists but stock is
   tracked per product.
3. **Price lists are inert.** `price_lists` stores rules as JSONB but the
   CommercialEngine does not consult them yet — line pricing comes from the
   product or an explicit override.
4. **Single-currency arithmetic.** Currency is stored and returned per
   quote/order but there is no FX conversion; mixing currencies in one deal is
   not prevented.
5. **No background scheduler.** `CUSTOMER_RESPONSE_REQUIRED` staleness and
   invoice overdue transitions are computed on read rather than by a cron job.
6. **Attention items are computed at write time.** A policy changed *after* a
   quote was evaluated does not retroactively re-flag it until the quote is
   next touched.
7. **Idempotency keys are never garbage-collected.** `expires_at` is written
   but nothing prunes the table.
8. **`request-revision` returns the version to DRAFT** rather than forcing a
   new version. Defensible (no approval was granted), but a stricter
   interpretation would always create a version.
9. **No rate limiting or brute-force protection** on `/auth/login`.
10. **ADMIN can act on any approval step.** Convenient for the demo and
    audited, but a real deployment likely wants a separate break-glass role.
11. **Tests truncate the whole database between cases**, which is correct but
    makes the suite ~4 minutes rather than seconds.

## 25. P1 future work

Not started — P0 was the contract.

- **Product variants** — variant-level pricing and inventory.
- **Price lists** — wire tier pricing into the CommercialEngine.
- **Invoices + payments** — schema, endpoints and tests exist; the dunning
  lifecycle and PDF generation do not.
- **Recommendation engine** — `RecommendationEngine` is implemented
  (attach-rate cross-sell, margin repair, volume upsell) and served at
  `GET /quotes/{id}/recommendations`, but not yet wired into the quote builder.
- **Advanced fulfilment** — partial shipment tracking, carrier integration,
  delivery-promise dates.
- **What-if simulation** — run the PolicyEngine against a hypothetical version
  without persisting it. The engine is already pure, so this is mostly plumbing.
- **Deal replay / autopsy** — `commercial_snapshots` + `audit_events` already
  hold everything needed to reconstruct any past state.
- **Transactional outbox** — for eventual integration with external systems.

---

## Appendix A — Architecture decisions

Ambiguities in the spec, and what was chosen.

| # | Decision | Rationale |
|---|---|---|
| 1 | **`DISCOUNT_AMOUNT_AUTHORITY` policy type added** | The spec's demo needs Finance on a quote whose margin is healthy. Rather than hardcode "this quote needs Finance", a real signing-authority policy (total discount ≤ 20,000) is seeded and evaluated. Routing stays data-driven. |
| 2 | **Amount-unit policies contribute 0 to blended risk** | Mixing currency into a percentage-point score makes the number meaningless. They govern *who signs*, not *how risky*. |
| 3 | **`quote_service.py` and `order_service.py` added** | The plan folded versioning into `negotiation_service`. Separating them gives revision mechanics and order materialisation one owner each, which keeps the transaction boundaries obvious. |
| 4 | **`quote_lines.source_line_id` added** | Position-based line matching mis-reports add+remove as a product swap. Provenance makes the diff correct. |
| 5 | **Auto-approvals get an `approval_requests` row** | Otherwise a clean quote that is later revised has no decision to mark stale, and "who approved this?" has no answer. |
| 6 | **Cross-tenant reads return 404, not 403** | A 403 confirms the id exists, enabling enumeration. |
| 7 | **`current_version_number` (int) instead of an FK** | Avoids a circular foreign key between `quotes` and `quote_versions`; `(quote_id, version_number)` is uniquely indexed anyway. |
| 8 | **VARCHAR + CHECK instead of PostgreSQL ENUM** | Values stay readable in psql and adding one never needs `ALTER TYPE` in a migration. |
| 9 | **Python-side `onupdate` for `updated_at`** | A SQL-expression `onupdate` forces a post-fetch that leaves the attribute expired; the next read then attempts sync IO and raises `MissingGreenlet` on an AsyncSession. |
| 10 | **MANAGER may author deals** | Realistic. The self-approval check is what prevents abuse — authorship, not role, disqualifies an approver. |
| 11 | **Routers own `commit()`** | One visible transaction boundary per endpoint; services compose freely without nested-commit surprises. |
| 12 | **Money serialises as a JSON string** | A JSON number becomes an IEEE-754 double in any JS client and loses cents. |
| 13 | **Attention items raised only at decision points** | Raising them on every draft recalculation would make the Control Tower unreadable. |
| 14 | **Superseding a version retires its attention items** | Nobody can act on a problem in a replaced version. |
| 15 | **`session.add()` inside `begin_nested()`** | An object made pending *before* a savepoint survives its rollback, so the next flush retries the failing INSERT and poisons the transaction with `PendingRollbackError`. |
| 16 | **`NullPool` + 4-round bcrypt under test only** | asyncpg connections are loop-bound; and 12-round bcrypt across hundreds of users is minutes of pure KDF. Same code paths, unreachable outside tests. |

## Appendix B — Error codes

| Code | HTTP | Meaning |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | Payload failed schema validation |
| `BUSINESS_RULE_VIOLATION` | 400 | Operation violates a business rule |
| `AUTHENTICATION_FAILED` | 401 | Missing/invalid credentials or token |
| `WRONG_TOKEN_TYPE` | 401 | Refresh token used as access token, or vice versa |
| `USER_DISABLED` / `ORGANIZATION_DISABLED` | 401 | Principal deactivated |
| `FORBIDDEN` | 403 | Role may not perform this action |
| `PORTAL_USER_FORBIDDEN` | 403 | Customer reached an internal endpoint |
| `INTERNAL_USER_FORBIDDEN` | 403 | Employee reached a portal endpoint |
| `SELF_APPROVAL_FORBIDDEN` | 403 | Approver authored or submitted the quote |
| `WRONG_APPROVER_ROLE` | 403 | Wrong role for this approval step |
| `NOT_FOUND` | 404 | Missing, or outside your organization |
| `CONFLICT` | 409 | Generic state conflict |
| `IMMUTABLE_VERSION` | 409 | Version is not DRAFT |
| `VERSION_TERMINAL` | 409 | CONFIRMED/REJECTED/SUPERSEDED — immutable forever |
| `VERSION_NOT_DRAFT` / `VERSION_NOT_APPROVED` / `VERSION_NOT_SENT` | 409 | Wrong state for the transition |
| `STALE_APPROVAL` | 409 | A material change invalidated the approval |
| `APPROVAL_REQUIRED` | 409 | Not approved yet |
| `APPROVAL_NOT_PENDING` / `NO_PENDING_STEP` | 409 | Already decided |
| `ALREADY_CONFIRMED` | 409 | Quote version already converted to an order |
| `DUPLICATE_OPERATION` | 409 | Already performed |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Same key, different body |
| `IDEMPOTENT_REQUEST_IN_FLIGHT` | 409 | Identical request still processing |
| `INSUFFICIENT_INVENTORY` | 409 | Not enough stock |
| `STOCK_BELOW_RESERVED` / `STOCK_NEGATIVE` | 409 | Illegal stock adjustment |
| `OVERRIDE_EXCEEDS_LINE` | 400 | Manual allocation exceeds the line |
| `NOTHING_TO_FULFILL` | 409 | No allocated stock to ship |
| `EMPTY_QUOTE` / `EMPTY_REVISION` | 400 | A quote needs at least one line |
| `OVERPAYMENT` | 400 | Payment exceeds the balance |
| `EMAIL_ALREADY_REGISTERED` | 409 | Duplicate signup |
| `ROLE_ORG_MISMATCH` | 400 | Portal role in a seller org, or vice versa |

## Appendix C — Endpoint map

**Phase 1 — Foundation**
`POST /auth/signup` · `POST /auth/login` · `POST /auth/refresh` ·
`GET /users/me` · `GET|POST /users` ·
`POST /admin/products` · `GET /products` ·
`POST /admin/warehouses` · `GET /warehouses` ·
`POST /admin/policies` · `GET /policies` ·
`POST /admin/inventory` · `POST /admin/inventory/adjust` · `GET /inventory` ·
`POST /admin/seed`

**Phase 2 — Commercial core**
`POST|GET /customers` · `GET|PATCH /customers/{id}` ·
`GET|POST /customers/{id}/contacts` ·
`POST|GET /deals` · `GET|PATCH /deals/{id}` ·
`POST /deals/{id}/quotes` · `GET /quotes/{id}` · `GET /quote-versions/{id}` ·
`POST /quote-versions/{id}/lines` ·
`PATCH|DELETE /quote-versions/{id}/lines/{line_id}` ·
`POST /quote-versions/{id}/calculate` ·
`GET /quote-versions/{id}/policy-results`

**Phase 3 — Decision Fabric**
`POST /quote-versions/{id}/submit` · `GET /quote-versions/{id}/impact` ·
`GET /quote-versions/{id}/approval`

**Phase 4 — Approvals**
`GET /approvals/inbox` · `GET /approvals/{id}` ·
`POST /approvals/{id}/approve` · `POST /approvals/{id}/reject` ·
`POST /approvals/{id}/request-revision`

**Phase 5 — Negotiation + portal**
`POST /quote-versions/{id}/revisions` · `POST /quote-versions/{id}/send` ·
`GET /portal/quotes` · `GET /portal/quotes/{id}` ·
`GET|POST /portal/quotes/{id}/messages` ·
`GET /quotes/{id}/negotiation` · `POST /quotes/{id}/negotiation/reply`

**Phase 6 — Confirmation + orders**
`POST /portal/quotes/{id}/confirm` · `GET /orders` · `GET /orders/{id}` ·
`GET /orders/{id}/allocations` · `POST /orders/{id}/allocate` ·
`POST /orders/{id}/fulfill`

**Phase 7 — Billing + Control Tower**
`GET /billing/schedules` · `GET /billing/orders/{id}/summary` ·
`GET /billing/proration-preview` ·
`GET /dashboard/control-tower` · `GET /dashboard/attention-items` ·
`POST /dashboard/attention-items/{id}/resolve` ·
`GET /dashboard/deal-health` · `GET /dashboard/deal-health/{id}` ·
`GET /audit/events` · `GET /audit/quotes/{id}/timeline`

**P1**
`POST|GET|PATCH /admin/product-variants[/{id}]` ·
`POST|GET|PATCH /admin/price-lists[/{id}]` ·
`GET /products/{id}/variants` ·
`POST|GET /billing/invoices` · `POST /billing/invoices/{id}/payments` ·
`POST /billing/invoices/{id}/void` ·
`GET /quotes/{id}/recommendations` ·
`POST /quotes/{id}/recommendations/{product_id}/dismiss`

**Phase 8 — Lists, configuration and reporting**
`GET /quotes` · `PATCH /quote-versions/{id}/discount` ·
`POST /quotes/{id}/lose` · `POST /quote-versions/{id}/simulate` ·
`GET|PATCH /admin/settings` ·
`POST|GET|PATCH /admin/sales-teams[/{id}]` ·
`POST|DELETE /admin/sales-teams/{id}/members[/{user_id}]` ·
`GET|PATCH /admin/warehouses/{id}` ·
`GET /reports/sales-performance` · `GET /reports/approval-status` ·
`GET /reports/products` · `GET /reports/discounts` ·
`GET /reports/pipeline` · `GET /reports/discount-anomalies` ·
`GET /reports/{report}/export` · `GET /reports/export/formats`

**Phase 9 — Subscription lifecycle and fulfilment**
`POST /billing/subscriptions/{id}/change` ·
`POST /billing/subscriptions/{id}/cancel` ·
`GET /billing/credit-notes[/{id}]` ·
`POST /billing/credit-notes/{id}/refund` ·
`POST /billing/credit-notes/{id}/void` ·
`PATCH /orders/{id}/promise` ·
`POST /orders/{id}/fulfillments/{fid}/deliver` ·
`POST /orders/{id}/cancel` ·
`POST /dashboard/attention-items/{id}/acknowledge` ·
`POST /dashboard/attention-items/{id}/nudge` ·
`POST /dashboard/attention-items/{id}/escalate`

**System**
`GET /health` · `GET /docs` · `GET /redoc` · `GET /openapi.json`

---

## Appendix D — The five added tables

33 → 38. All four migrations are additive, with server defaults on every new
`NOT NULL` column so existing rows are safe.

| Table | Why |
|---|---|
| `organization_settings` | PDF A3 requires a configurable approval chain and B9 a *configured* stalled-deal window. Both were process-global environment variables, which cannot differ per tenant. One row per organization, created lazily from the environment defaults so existing tenants behave exactly as before. |
| `sales_teams` · `sales_team_members` | PDF A7.4 filters reports by "Sales Team / Rep". `deals.owner_user_id` gave Rep; Team had no entity. Membership is many-to-many because a rep can sit on a regional and a vertical team at once. |
| `credit_notes` | PDF A5/B7 require cancellation with a partial refund or credit note. An issued invoice is a financial record, so the credit is a separate document rather than an edit to the original. |
| `dismissed_recommendations` | PDF B5 gives the upsell panel a Dismiss button. Without persistence the suggestion reappears and the button looks broken. Scoped per version, because a revision is a fresh proposal. |

## Appendix E — Test suite performance

The suite was ~8x slower than necessary. Two fixes, both worth knowing if it
regresses:

1. **Connection pooling.** The engine forced `NullPool` under test, opening a fresh TCP connection and authentication handshake for **every statement** — 133 ms/query measured against Dockerised PostgreSQL versus 4.8 ms pooled. The workaround existed because asyncpg binds a connection to its creating event loop; setting `asyncio_default_test_loop_scope = session` in `pytest.ini` means there is only ever one loop, so pooling is safe. `DB_FORCE_NULLPOOL=true` restores the old behaviour.
2. **Cleanup strategy.** The per-test fixture truncated all 38 tables unconditionally. `TRUNCATE` rewrites each relation file and syncs the data directory, benchmarking at a flat ~2.7s irrespective of table count. The fixture now finds dirty tables in one query and uses `DELETE` with foreign-key triggers suspended for the transaction.

`test_auth.py` (18 tests): **101.4s → 16.2s**. Full suite: **~45 min projected
→ 6.6 min** for 433 tests.
