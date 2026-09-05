# SYSTEM ARCHITECTURE

Satisfies PDF §8 deliverable D3: *"A one-page architecture diagram showing the
data model and how the major modules connect."*

Stack: Python 3.13 · FastAPI 0.115 · SQLAlchemy 2.0 async (asyncpg) ·
Pydantic v2 · Alembic 1.14 · PostgreSQL 16 · JWT (python-jose) · bcrypt (passlib).

---

## 1. The one-page diagram

```mermaid
flowchart TB
    subgraph users [1 · Users]
        direction LR
        U1[SALES]
        U2[MANAGER]
        U3[FINANCE]
        U4[OPS]
        U5[ADMIN]
        U6[CUSTOMER<br/>external]
    end

    subgraph fe [2 · Frontend Application - to be built]
        direction LR
        FE1[Backend Config Area<br/>modules A1-A7]
        FE2[Rep Workspace<br/>modules B1-B7, B9]
        FE3[Customer Portal<br/>module B8 - separate shell]
    end

    subgraph edge [3 · HTTP Edge]
        CORS[CORSMiddleware]
        EXC["Exception handlers<br/>single error envelope"]
        OAPI["/docs · /redoc · /openapi.json"]
        HLTH["/health"]
    end

    subgraph authz [4 · Authentication and Authorization]
        JWT["middleware/auth.py<br/>typed JWT · bcrypt"]
        DEPS["dependencies.py<br/>InternalUser · CustomerUser<br/>SalesUser · ApproverUser · AdminUser"]
        TEN["middleware/tenant.py<br/>org scoping · 404 not 403"]
    end

    subgraph routers [5 · Routers - validate, delegate, own the commit]
        direction LR
        R1[auth · users · admin]
        R2[products · policies · inventory]
        R3[customers · deals · quotes]
        R4[approvals · negotiations]
        R5[orders · billing · dashboard]
    end

    subgraph services [6 · Business Logic - all rules live here]
        direction TB
        CE["CommercialEngine<br/>only writer of money columns"]
        PE["PolicyEngine<br/>ceilings · blended risk · routing"]
        DF["DecisionFabric<br/>change detection · staleness"]
        AS["ApprovalService<br/>ordered steps · confirmation gate"]
        NS["NegotiationService<br/>portal · counter-offers"]
        QS["QuoteService<br/>versioning · immutability"]
        OS["OrderService<br/>quote to order"]
        IS["InventoryService<br/>FOR UPDATE allocation"]
        BS["BillingService<br/>schedules · proration"]
        DS["DashboardService<br/>Control Tower · deal health"]
        AUD["AuditService<br/>append-only trail"]
        IDEM["IdempotencyService<br/>at-most-once"]
        RE["RecommendationEngine<br/>upsell · cross-sell"]
        IDS["IdentityService<br/>orgs · roles · users"]
    end

    subgraph bus [7 · In-Process Event Bus]
        EV["events.py<br/>25 EventTypes<br/>handlers run in the caller's transaction"]
    end

    subgraph data [8 · PostgreSQL 16 - 33 tables]
        direction LR
        D1["Identity 4<br/>orgs · roles · users · contacts"]
        D2["Commercial 5<br/>profiles · products · variants<br/>price_lists · deals"]
        D3["Quotes 3<br/>quotes · versions · lines"]
        D4["Governance 3<br/>policies · results · snapshots"]
        D5["Approvals 3<br/>requests · steps · decisions"]
        D6["Tracking 2<br/>impacts · attention_items"]
        D7["Negotiation 2<br/>threads · messages"]
        D8["Execution 3<br/>orders · lines · fulfillments"]
        D9["Inventory 3<br/>warehouses · inventory · allocations"]
        D10["Billing 3<br/>schedules · invoices · payments"]
        D11["System 2<br/>audit_events · idempotency_keys"]
    end

    subgraph ext [9 · External Services]
        NONE["NONE<br/>no broker · no cache · no object store<br/>no email · no payment gateway<br/>deliberate: nothing the PDF requires needs one"]
    end

    U1 & U2 & U3 & U4 & U5 --> FE1 & FE2
    U6 --> FE3
    FE1 & FE2 & FE3 -->|"HTTPS JSON · Bearer token"| edge
    edge --> authz
    authz --> routers
    routers --> services
    services --> bus
    bus -->|"every event writes an audit row"| AUD
    services --> data
    AUD --> D11
    services -.-> ext
```

**Why layer 9 is empty.** Every requirement in the PDF is satisfiable in-process.
An event broker, cache, or object store would add operational surface without
serving a stated requirement — see [`PROBLEM_ANALYSIS.md`](./PROBLEM_ANALYSIS.md)
§F "UNNECESSARY". The event bus runs handlers on the caller's session so an
audit record and the state change it describes commit or roll back together;
a broker would break exactly that guarantee.

---

## 2. Layering rules

```mermaid
flowchart LR
    HTTP[HTTP request] --> RT[Router]
    RT -->|"validate payload<br/>resolve role dependency"| SV[Service]
    SV -->|"typed error from errors.py"| RT
    SV --> ORM[SQLAlchemy models]
    ORM --> PG[(PostgreSQL)]
    SV --> EVB[Event bus]
    EVB --> AUDIT[audit_events]
    RT -->|"owns commit"| PG
    PG -->|"CHECK / UNIQUE / FK violation"| SV
```

| Rule | Rationale |
|---|---|
| Routers never contain business rules | They validate input, call one service, and own `commit()`. The transaction boundary is visible in one place per endpoint. |
| Services never return HTTP concerns | They raise typed errors from [`app/errors.py`](../app/errors.py) which map to one JSON envelope via three exception handlers in [`app/main.py`](../app/main.py). |
| The database is the last line of defence | Where an invariant can be a constraint, it is — so an application bug produces a failed transaction rather than corrupt commercial data. |
| `CommercialEngine` is the only writer of financial columns | One place to audit money arithmetic. |
| Event handlers run inline on the caller's session | Audit and business state cannot drift. Handler failure fails the operation on purpose. |

---

## 3. Request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant CORS as CORSMiddleware
    participant B as HTTPBearer
    participant D as get_current_user
    participant R as require_* guard
    participant H as Route handler
    participant S as Service
    participant DB as PostgreSQL
    participant E as Event bus

    C->>CORS: request + Bearer token
    CORS->>B: extract credentials (auto_error=False)
    B->>D: token or None
    alt no token
        D-->>C: 401 AUTHENTICATION_FAILED "Missing bearer token."
    end
    D->>D: decode_token(expected_type="access")
    alt invalid / expired / wrong type
        D-->>C: 401 AUTHENTICATION_FAILED / WRONG_TOKEN_TYPE
    end
    D->>DB: SELECT user JOIN role JOIN organization
    Note over D,DB: re-read every request so deactivation<br/>and role change apply immediately
    alt user or org disabled
        D-->>C: 401 USER_DISABLED / ORGANIZATION_DISABLED
    end
    D->>R: User
    alt role not allowed
        R-->>C: 403 FORBIDDEN + your_role + allowed_roles
    end
    R->>H: authorized User
    H->>S: delegate
    S->>DB: scoped query (organization_id)
    alt row missing or other org
        S-->>C: 404 NOT_FOUND (never 403)
    end
    S->>DB: mutate
    S->>E: emit(DomainEvent)
    E->>DB: INSERT audit_events (same transaction)
    S-->>H: domain object
    H->>DB: COMMIT
    H-->>C: Pydantic response model
```

---

## 4. Feature relationship diagram

```mermaid
flowchart TB
    ORG[Organization<br/>SELLER or CUSTOMER] -->|owns| USER[User]
    USER -->|has| ROLE[Role<br/>6 RoleCodes]
    ORG -->|"seller defines"| PROFILE[CustomerProfile<br/>tier · terms · credit]
    PROFILE -->|"belongs to buyer"| ORG
    PROFILE --> CONTACT[Contact]

    ORG -->|configures| PRODUCT[Product<br/>category · price · cost · billing_type]
    PRODUCT --> VARIANT[ProductVariant<br/>INERT - not used in pricing]
    ORG --> PRICELIST[PriceList<br/>INERT - not read by engine]
    ORG --> POLICY[Policy<br/>ceiling · margin floor · authority]
    ORG --> WAREHOUSE[Warehouse<br/>priority · shipping cost]
    WAREHOUSE --> INV[Inventory<br/>on_hand · reserved · available]

    USER -->|owns| DEAL[Deal<br/>stage]
    PROFILE --> DEAL
    DEAL --> QUOTE[Quote<br/>status · current_version_number]
    QUOTE --> QV[QuoteVersion<br/>8 statuses · totals · risk]
    QV -->|parent_version_id| QV
    QV --> QL[QuoteLine<br/>source_line_id for provenance]
    PRODUCT --> QL

    QV -->|calculated by| CE[CommercialEngine]
    CE --> SNAP[CommercialSnapshot<br/>JSONB point-in-time]
    QV -->|evaluated by| PE[PolicyEngine]
    POLICY --> PE
    PROFILE -->|tier sensitivity| PE
    PE --> PR[PolicyResult<br/>explainable per line]
    PE -->|"required levels"| AR[ApprovalRequest]
    AR --> AST[ApprovalStep<br/>ordered by sequence]
    AST --> AD[ApprovalDecision<br/>actor · reason · snapshot]
    USER --> AD

    QV -->|revision| DF[DecisionFabric]
    DF --> DI[DecisionImpact<br/>every diff, material or not]
    DF -->|"material change"| AR
    DF --> AI[AttentionItem<br/>why · impact · owner · next]

    QV -->|send| THREAD[NegotiationThread]
    THREAD --> MSG[NegotiationMessage<br/>comment · question · counter]
    MSG -->|"counter-offer creates"| QV

    QV -->|confirm| SO[SalesOrder<br/>UNIQUE quote_version_id]
    SO --> SOL[SalesOrderLine]
    QL --> SOL
    SOL --> ALLOC[InventoryAllocation<br/>reserved or backordered]
    INV --> ALLOC
    ALLOC --> FUL[Fulfillment<br/>one per warehouse]
    WAREHOUSE --> FUL

    SOL --> BSCH[BillingSchedule<br/>one-time or per period]
    BSCH --> INVOICE[Invoice]
    INVOICE --> PAY[Payment]

    DEAL --> AI
    QUOTE --> AI
    AI --> CT[Control Tower]
    DEAL --> HEALTH[Deal Health Score]

    AR --> AUDIT[(audit_events<br/>append-only · monotonic sequence)]
    QV --> AUDIT
    SO --> AUDIT
    MSG --> AUDIT
```

---

## 5. The governance core

This is the part that answers PDF §1's "self governing deal engine" claim.

```mermaid
flowchart TD
    START([Quote version changes]) --> CALC["CommercialEngine.calculate_version<br/>per-line arithmetic, ROUND_HALF_UP<br/>round per line then sum"]
    CALC --> SNAP[("commercial_snapshots<br/>is_current = true")]
    CALC --> EVAL["PolicyEngine.evaluate<br/>resolve ceiling per line by<br/>tier x category, most specific wins"]

    EVAL --> C1["C1 weighted discount overage<br/>sum of overage x revenue_share x 3.0<br/>cap 45"]
    EVAL --> C2["C2 breadth<br/>violating_lines x 5.0<br/>cap 15"]
    EVAL --> C3["C3 margin shortfall<br/>max(0, floor - actual) x 5.0<br/>cap 40"]
    EVAL --> C4["C4 discount depth<br/>effective_discount_pct x 0.4<br/>cap 15"]

    C1 & C2 & C3 & C4 --> SCORE["score = min(100, sum x tier_sensitivity)<br/>PLATINUM 1.20 GOLD 1.10<br/>SILVER 1.00 BRONZE 0.95"]
    SCORE --> BAND{Band}
    BAND -->|0| NONE[NONE]
    BAND -->|"0-15"| LOW[LOW]
    BAND -->|"15-40"| MED[MEDIUM]
    BAND -->|"40-70"| HIGH[HIGH]
    BAND -->|">=70"| CRIT[CRITICAL]

    EVAL --> ROUTE["required = union of required_action<br/>from VIOLATED policies"]
    SCORE --> ESC{"score >= 60?"}
    ESC -->|Yes| ADDFIN["add FINANCE"]
    ROUTE --> STEPS["steps in escalation order<br/>SALES_MANAGER then FINANCE"]
    ADDFIN --> STEPS

    START --> DIFF{"previous version exists?"}
    DIFF -->|Yes| DETECT["DecisionFabric.detect_changes<br/>match lines by source_line_id<br/>not by position"]
    DETECT --> MAT{"material?<br/>fail-closed with epsilons"}
    MAT -->|No| RECORD[("decision_impacts<br/>material = false")]
    MAT -->|Yes| STALE["prior APPROVED request to STALE<br/>kept, never deleted"]
    STALE --> BLOCK["version.is_stale = true<br/>confirmation blocked 409"]
    STALE --> ALERT["CRITICAL attention item<br/>owner FINANCE"]
    STALE --> STEPS

    STEPS --> PENDING["version PENDING_APPROVAL"]
    ROUTE -->|"no violations"| AUTO["version APPROVED<br/>request row with 0 steps<br/>so staleness has a target later"]
```

**Amount-unit policies contribute 0 to the score.** Signing authority is a
question of *who* must approve, not *how risky* the deal is; mixing currency into
a percentage-point score would make the number meaningless. They still route
approvals — which is how the canonical demo pulls in Finance on a quote whose
margin is perfectly healthy.

---

## 6. Event flow

25 `EventType` values, one global subscriber that writes an `audit_events` row.

```mermaid
flowchart LR
    subgraph emit [Emitters]
        A["IdentityService"] --> E1["USER_SIGNED_UP<br/>USER_LOGGED_IN"]
        B["QuoteService"] --> E2["QUOTE_CREATED · QUOTE_SUBMITTED<br/>QUOTE_APPROVED · QUOTE_SENT<br/>QUOTE_REVISED"]
        C["DecisionFabric"] --> E3["POLICY_EVALUATED<br/>MATERIAL_CHANGE_DETECTED"]
        D["ApprovalService"] --> E4["APPROVAL_REQUESTED · APPROVAL_GRANTED<br/>APPROVAL_REJECTED · APPROVAL_REVISION_REQUESTED<br/>APPROVAL_MARKED_STALE · QUOTE_APPROVED"]
        F["NegotiationService"] --> E5["CUSTOMER_COMMENTED<br/>CUSTOMER_COUNTERED"]
        G["OrderService"] --> E6["QUOTE_CONFIRMED<br/>ORDER_CREATED"]
        H["InventoryService"] --> E7["INVENTORY_ALLOCATED<br/>INVENTORY_SHORTAGE<br/>ORDER_FULFILLED"]
        I["BillingService"] --> E8["BILLING_SCHEDULED"]
        J["AttentionService"] --> E9["ATTENTION_ITEM_CREATED<br/>ATTENTION_ITEM_RESOLVED"]
    end

    E1 & E2 & E3 & E4 & E5 & E6 & E7 & E8 & E9 --> BUS["events.emit(session, event)"]
    BUS --> GLOBAL["@subscribe_all<br/>_write_audit_event"]
    GLOBAL --> ROW[("audit_events<br/>sequence · actor · payload JSONB<br/>money as strings")]
    BUS --> SPECIFIC["per-type handlers"]
```

`sequence` is a monotonic `BIGINT IDENTITY` because a single transaction emits
half a dozen events sharing the same microsecond; it gives a stable total
ordering for the timeline endpoint.

Money in payloads is stored as **strings**. A float round-trip through JSONB
would corrupt the record of a decision.

---

## 7. Tenant isolation

```mermaid
flowchart TD
    REQ[Authenticated request] --> KIND{"role in INTERNAL_ROLES?"}

    KIND -->|Yes| SCOPE["scope_to_org(stmt, model, user.organization_id)"]
    SCOPE --> FOUND{"row found in own org?"}
    FOUND -->|Yes| OK[200]
    FOUND -->|"No, or other org"| NF["404 NOT_FOUND<br/>never 403"]

    KIND -->|"No, CUSTOMER"| PORTAL["NegotiationService.authorize"]
    PORTAL --> CHECK{"quote issued to<br/>customer_organization_id<br/>AND thread exists?"}
    CHECK -->|Yes| REDACT["*PublicRead schemas<br/>cost/margin/risk fields<br/>do not exist"]
    CHECK -->|No| NF2["404 with details.reason<br/>'not issued to your organization'"]
    REDACT --> OK
```

**Why 404 and not 403.** A 403 confirms the id exists, enabling enumeration. All
cross-tenant access returns 404. `TenantIsolationError` exists in
[`app/errors.py`](../app/errors.py) but is deliberately never raised.

**Two different isolation mechanisms.** Internal users match on
`organization_id`. Customer portal users never match on `organization_id` at all
— their access comes through `customer_profiles.customer_organization_id`,
checked explicitly by `NegotiationService.authorize`.

---

## 8. Concurrency and idempotency

```mermaid
flowchart TB
    subgraph alloc [Inventory allocation]
        A1["POST /orders/id/allocate"] --> A2["lines sorted by product_id"]
        A2 --> A3["SELECT ... FOR UPDATE<br/>all stock rows for the product<br/>ordered by inventory.id"]
        A3 --> A4["identical lock order in every txn<br/>removes the deadlock window"]
        A4 --> A5["decide split against locked rows"]
        A5 --> A6["CHECK quantity_reserved <= quantity_on_hand"]
        A6 --> A7["COMMIT"]
    end

    subgraph idem [Idempotent confirmation]
        B1["POST /portal/quotes/id/confirm<br/>+ Idempotency-Key"] --> B2["fingerprint = SHA-256 of canonical body"]
        B2 --> B3["SELECT FOR UPDATE on<br/>(org, endpoint, key)"]
        B3 --> B4{state}
        B4 -->|"new"| B5["INSERT IN_PROGRESS<br/>proceed"]
        B4 -->|"COMPLETED"| B6["replay stored response_body<br/>idempotent_replay true"]
        B4 -->|"IN_PROGRESS"| B7["409 IDEMPOTENT_REQUEST_IN_FLIGHT"]
        B4 -->|"FAILED"| B8["reset to IN_PROGRESS, retry"]
        B4 -->|"hash differs"| B9["409 IDEMPOTENCY_KEY_REUSED"]
        B5 --> B10["UNIQUE sales_orders.quote_version_id<br/>final backstop above the idempotency layer"]
    end
```

Two independent layers protect confirmation. Even with no `Idempotency-Key`, the
`UNIQUE` constraint on `sales_orders.quote_version_id` makes a duplicate order
impossible; the loser of the race returns the existing order rather than an error.

---

## 9. Module boundaries mapped to PDF modules

```mermaid
flowchart LR
    subgraph A [PDF Group A · Sales Backend]
        A1[A1 Auth] --> SVC1[IdentityService<br/>middleware/auth]
        A2[A2 Products and Price Lists] --> SVC2["admin router<br/>Product · Variant INERT · PriceList INERT"]
        A3[A3 Discount Tiers and Chains] --> SVC3[PolicyEngine<br/>Policy model]
        A4[A4 Warehouses] --> SVC4[InventoryService<br/>Warehouse · Inventory]
        A5[A5 Subscription Plans] --> SVC5["BillingService<br/>PARTIAL - no apply/cancel"]
        A6[A6 Upsell Rules OPTIONAL] --> SVC6["RecommendationEngine<br/>PARTIAL - rules not co-purchase"]
        A7[A7 Reporting] --> SVC7["MISSING ENTIRELY"]
    end

    subgraph B [PDF Group B · Rep Workspace]
        B1[B1 Top Menu] --> SB1["deals router<br/>MISSING flat quote list"]
        B2[B2 Quotation List and Pipeline] --> SB2["MISSING GET /quotes"]
        B3[B3 Quotation Builder] --> SB3["QuoteService · CommercialEngine<br/>MISSING order-level discount"]
        B4[B4 Approval Screen] --> SB4[ApprovalService<br/>COMPLETE]
        B5[B5 Upsell Panel] --> SB5["RecommendationEngine<br/>MISSING promotion tag · dismiss"]
        B6[B6 Warehouse Split] --> SB6[InventoryService<br/>COMPLETE]
        B7[B7 Subscription and Billing] --> SB7["BillingService<br/>MISSING proration apply · cancel · credit note"]
        B8[B8 Customer Portal] --> SB8[NegotiationService<br/>COMPLETE]
        B9[B9 Deal Health and Anomaly] --> SB9["DashboardService<br/>MISSING anomaly · slippage · nudge"]
    end
```

Full traceability in [`REQUIREMENT_TRACEABILITY_MATRIX.md`](./REQUIREMENT_TRACEABILITY_MATRIX.md).

---

## 10. Deployment topology

```mermaid
flowchart LR
    subgraph dev [Hackathon / development]
        FE1["Frontend dev server"] -->|"127.0.0.1:8000"| API1["uvicorn app.main:app --reload"]
        API1 -->|"asyncpg :5433"| PG1[("postgres:16-alpine<br/>docker compose<br/>mydb + mydb_test")]
    end

    subgraph prod [Production shape - not built]
        CDN["Static frontend"] --> LB["TLS terminator"]
        LB --> APIN["uvicorn workers<br/>behind gunicorn"]
        APIN --> PGP[("managed PostgreSQL 16<br/>pool_size 10 · max_overflow 20")]
        APIN -.->|"needed at scale"| RL["rate limiter · token store"]
    end
```

`docker-compose.yml` publishes PostgreSQL on **5433** to avoid clashing with a
local install and creates `mydb_test` on first boot via
`scripts/init_test_db.sql`. `app/config.py` rejects any `DATABASE_URL` that is
not `postgresql+asyncpg://`, so the app cannot be started against SQLite by
accident.

---

## 11. Configuration surface

All settings are environment-driven via `pydantic-settings`; no credential or
tunable is hardcoded in business code.

| Group | Variables |
|---|---|
| App | `APP_NAME` `APP_VERSION` `ENVIRONMENT` `DEBUG` `API_PREFIX` |
| Database | `DATABASE_URL` `TEST_DATABASE_URL` `DB_POOL_SIZE` `DB_MAX_OVERFLOW` `DB_ECHO` |
| JWT | `JWT_SECRET_KEY` `JWT_ALGORITHM` `ACCESS_TOKEN_EXPIRE_MINUTES` `REFRESH_TOKEN_EXPIRE_DAYS` `BCRYPT_ROUNDS` |
| CORS | `CORS_ORIGINS` |
| Commercial | `DEFAULT_TAX_RATE_PCT` `MONEY_DECIMAL_PLACES` |
| Risk weights | `RISK_DISCOUNT_OVERAGE_WEIGHT` `RISK_BREADTH_WEIGHT` `RISK_MARGIN_WEIGHT` `RISK_DEPTH_WEIGHT` `RISK_FINANCE_ESCALATION_THRESHOLD` |
| Seed | `SEED_DEFAULT_PASSWORD` |

**Architectural gap.** The risk weights and the finance escalation threshold are
process-global environment variables. PDF A3 requires the approval chain to be
**configurable per organization**, and B9 requires a **configured** stalled-deal
window (currently the module constant `NO_RESPONSE_DAYS = 14`). These belong in a
per-tenant settings table. Tracked as P0 in
[`BACKEND_GAP_ANALYSIS.md`](./BACKEND_GAP_ANALYSIS.md).

---

## 12. What the architecture deliberately does not have

| Absent | Reason |
|---|---|
| Message broker | In-process events keep audit and state in one transaction. A broker would break that guarantee to solve a problem this system does not have. |
| Redis / cache layer | No read path is hot enough to justify cache-invalidation complexity on governed financial data. |
| Object storage / file upload | No PDF requirement involves file upload. Verified: zero `UploadFile`, `FileResponse` or `StreamingResponse` in the codebase. |
| WebSocket / SSE | Verified absent. "Real time" in the PDF means recomputed-on-read, which the request/response cycle satisfies. Frontend uses refetch-on-action plus optional polling. |
| Background scheduler | Stalled-deal and overdue-invoice states are computed on read. Honest limitation; a cron would be needed for outbound nudges. |
| Email / SMS delivery | The portal is the PDF's explicit replacement for email. |
| Payment gateway | PDF QT8 requires *recording* a payment and updating invoice status, not processing one. |
| Multi-currency FX | PDF §7 calls it a bonus. Currency is stored per quote and order; no conversion. |
