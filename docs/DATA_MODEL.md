# DATA MODEL

33 tables in PostgreSQL 16. Verified against [`app/models/`](../app/models/),
the `EXPECTED_TABLES` constant in [`app/models/__init__.py`](../app/models/__init__.py),
and migrations `91563b112f87` (initial, 33 tables) and `26bdcb293597`
(`quote_lines.source_line_id`).

`python -m scripts.verify_db` asserts: 33 tables, 112 foreign keys across 31
tables, 645 constraints, 205 indexes, **zero float/double columns** (95 NUMERIC
money columns), and all timestamps timezone-aware.

---

## 1. Column type conventions

Defined in [`app/models/base.py`](../app/models/base.py).

| Alias | SQL type | Used for |
|---|---|---|
| `Money` | `NUMERIC(18, 2)` | Amounts and totals |
| `UnitMoney` | `NUMERIC(18, 4)` | Unit prices and costs |
| `Percent` | `NUMERIC(9, 4)` | Percentages and risk scores |
| `Quantity` | `NUMERIC(18, 4)` | Quantities |
| `Factor` | `NUMERIC(12, 8)` | Proration factors |
| `Str32/64/128/255` | `VARCHAR(n)` | Bounded strings |
| `LongText` | `TEXT` | Reasons, notes, explanations |
| `JsonDict` / `JsonList` | `JSONB` | Structured payloads |

**No floating-point column exists anywhere.** A margin decision cannot rest on
IEEE-754 drift.

### Mixins

| Mixin | Adds |
|---|---|
| `UUIDPrimaryKeyMixin` | `id UUID PRIMARY KEY DEFAULT uuid4` |
| `TimestampMixin` | `created_at TIMESTAMPTZ NOT NULL` (indexed), `updated_at TIMESTAMPTZ NOT NULL` with Python-side `onupdate` |
| `CreatedAtMixin` | `created_at` only — used by append-only tables so there is nothing to rewrite history with |
| `OrgOwnedMixin` | `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT` (indexed) |

`updated_at` uses a Python-side `onupdate` rather than a SQL expression: a
SQL-expression `onupdate` forces a post-fetch that leaves the attribute expired,
and the next read then attempts sync IO and raises `MissingGreenlet` on an
`AsyncSession`.

### Enum storage

Every enum column is `VARCHAR(48)` plus a named `CHECK` constraint
(`native_enum=False`), not a PostgreSQL `ENUM` type. Values stay readable in
`psql` and adding one never requires `ALTER TYPE` in a migration.

---

## 2. Relationships in plain English

```
Organization (SELLER)
 ├── owns → Users ── has → Role
 ├── configures → Products ── has → ProductVariants
 ├── configures → PriceLists
 ├── configures → Policies              (discount ceilings, margin floor, signing authority)
 ├── configures → Warehouses ── stocks → Inventory
 └── maintains → CustomerProfiles ── point at → Organization (CUSTOMER)
                  ├── has → Contacts
                  └── is the buyer on → Deals

Deal (owned by a User)
 └── contains → Quotes
                 └── contains → QuoteVersions        (immutable once submitted)
                                 ├── parent_version_id → itself      (revision chain)
                                 ├── contains → QuoteLines
                                 │                └── source_line_id → itself  (provenance)
                                 ├── measured by → CommercialSnapshot
                                 ├── judged by → PolicyResults
                                 ├── diffed into → DecisionImpacts
                                 ├── gated by → ApprovalRequest
                                 │                ├── ordered → ApprovalSteps
                                 │                ├── records → ApprovalDecisions
                                 │                └── superseded_by_request_id → itself
                                 ├── discussed in → NegotiationThread → NegotiationMessages
                                 └── becomes → SalesOrder            (exactly one, ever)

SalesOrder
 ├── contains → SalesOrderLines
 │                └── reserved by → InventoryAllocations → Inventory / Warehouse
 ├── shipped as → Fulfillments        (one per warehouse)
 └── billed by → BillingSchedules
                  └── invoiced as → Invoices
                                     └── settled by → Payments

Everything                     → AuditEvents        (append-only, monotonic sequence)
Anything needing attention     → AttentionItems     (why, impact, owner, next action)
Retryable POSTs                → IdempotencyKeys
```

**The three self-referential links carry the governance semantics:**

| Link | Purpose |
|---|---|
| `quote_versions.parent_version_id` | The revision chain. Lets you walk back to the terms that were originally approved. |
| `quote_lines.source_line_id` | Line **provenance**. Matching lines by position would report an add-plus-remove as an innocuous product swap, hiding a real scope change from the approver. |
| `approval_requests.superseded_by_request_id` | Links a stale decision to the one that replaced it, so "who approved this, and was that still valid?" is answerable. |

---

## 3. Entity relationship diagram — identity and commercial

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : employs
    ROLES ||--o{ USERS : classifies
    ORGANIZATIONS ||--o{ CONTACTS : owns
    ORGANIZATIONS ||--o{ CUSTOMER_PROFILES : "seller maintains"
    ORGANIZATIONS ||--o{ CUSTOMER_PROFILES : "buyer is"
    CONTACTS |o--o| CUSTOMER_PROFILES : "primary contact"
    ORGANIZATIONS ||--o{ PRODUCTS : configures
    PRODUCTS ||--o{ PRODUCT_VARIANTS : "has variants"
    ORGANIZATIONS ||--o{ PRICE_LISTS : configures
    ORGANIZATIONS ||--o{ POLICIES : configures
    CUSTOMER_PROFILES |o--o{ POLICIES : "may scope"
    CUSTOMER_PROFILES ||--o{ DEALS : "buyer on"
    USERS ||--o{ DEALS : owns

    ORGANIZATIONS {
        uuid id PK
        varchar64 slug UK
        varchar48 kind "SELLER|CUSTOMER"
        varchar3 currency "USD"
        bool is_active
    }
    ROLES {
        uuid id PK
        varchar48 code UK "6 RoleCodes"
        bool is_internal
        bool can_approve
    }
    USERS {
        uuid id PK
        uuid organization_id FK
        varchar255 email UK
        varchar255 hashed_password
        uuid role_id FK
        bool is_active
        timestamptz last_login_at "nullable"
    }
    CUSTOMER_PROFILES {
        uuid id PK
        uuid organization_id FK "seller"
        uuid customer_organization_id FK "buyer"
        varchar48 tier "BRONZE|SILVER|GOLD|PLATINUM"
        varchar48 payment_terms "PREPAID..NET_90"
        numeric credit_limit "CHECK >= 0"
        numeric credit_used
        numeric tax_rate_pct
    }
    PRODUCTS {
        uuid id PK
        uuid organization_id FK
        varchar64 sku "UK per org"
        varchar48 category "HARDWARE|SOFTWARE|SERVICE|SUBSCRIPTION"
        numeric list_price "CHECK >= 0"
        numeric internal_cost "CHECK >= 0"
        varchar48 billing_type "ONE_TIME|RECURRING"
        varchar48 recurring_interval "nullable"
        bool is_stock_tracked
    }
    PRODUCT_VARIANTS {
        uuid id PK
        uuid product_id FK
        varchar64 sku "UK per org"
        jsonb attributes
        numeric price_delta
        numeric cost_delta
    }
    PRICE_LISTS {
        uuid id PK
        varchar64 code "UK per org"
        varchar48 tier "nullable"
        jsonb rules "INERT"
    }
    POLICIES {
        uuid id PK
        varchar64 code "UK per org"
        varchar48 policy_type
        varchar48 customer_tier "nullable"
        varchar48 product_category "nullable"
        numeric threshold_value
        varchar48 comparison "LTE|GTE"
        varchar48 unit "PERCENT|AMOUNT|DAYS"
        varchar48 required_action "ApprovalLevel"
        int priority "100"
    }
    DEALS {
        uuid id PK
        varchar64 reference "UK per org"
        uuid customer_profile_id FK
        uuid owner_user_id FK
        varchar48 stage "DealStage"
        numeric expected_value
        date expected_close_date "nullable"
    }
```

---

## 4. Entity relationship diagram — quotes and governance

```mermaid
erDiagram
    DEALS ||--o{ QUOTES : contains
    QUOTES ||--o{ QUOTE_VERSIONS : versions
    QUOTE_VERSIONS ||--o{ QUOTE_VERSIONS : "parent_version_id"
    QUOTE_VERSIONS ||--o{ QUOTE_LINES : lines
    QUOTE_LINES ||--o{ QUOTE_LINES : "source_line_id provenance"
    PRODUCTS ||--o{ QUOTE_LINES : prices
    QUOTE_VERSIONS ||--o{ COMMERCIAL_SNAPSHOTS : snapshots
    QUOTE_VERSIONS ||--o{ POLICY_RESULTS : evaluated
    POLICIES |o--o{ POLICY_RESULTS : produced
    QUOTE_VERSIONS ||--o{ DECISION_IMPACTS : diffed
    QUOTE_VERSIONS ||--o{ APPROVAL_REQUESTS : gated
    APPROVAL_REQUESTS ||--o{ APPROVAL_REQUESTS : "superseded_by"
    APPROVAL_REQUESTS ||--o{ APPROVAL_STEPS : ordered
    APPROVAL_STEPS ||--o{ APPROVAL_DECISIONS : records
    USERS ||--o{ APPROVAL_DECISIONS : decides
    QUOTES ||--|| NEGOTIATION_THREADS : "one thread"
    NEGOTIATION_THREADS ||--o{ NEGOTIATION_MESSAGES : messages
    NEGOTIATION_MESSAGES |o--o| QUOTE_VERSIONS : "triggered_version_id"

    QUOTES {
        uuid id PK
        varchar64 quote_number "UK per org"
        uuid deal_id FK
        varchar48 status "OPEN|CONFIRMED|LOST|CANCELLED"
        int current_version_number "int, not FK"
    }
    QUOTE_VERSIONS {
        uuid id PK
        uuid quote_id FK
        int version_number "UK with quote_id, CHECK >= 1"
        uuid parent_version_id FK "nullable, self"
        varchar48 status "8 QuoteVersionStatus"
        varchar48 source "INITIAL|INTERNAL_REVISION|CUSTOMER_COUNTER|APPROVER_REVISION_REQUEST"
        numeric gross_revenue
        numeric total_discount
        numeric net_revenue
        numeric tax_amount
        numeric total_revenue
        numeric total_cost
        numeric margin
        numeric margin_pct
        numeric effective_discount_pct
        numeric one_time_revenue
        numeric recurring_revenue
        numeric blended_risk_score
        varchar48 risk_band "RiskBand"
        bool requires_approval
        bool is_stale
        text stale_reason "nullable"
    }
    QUOTE_LINES {
        uuid id PK
        uuid quote_version_id FK
        uuid product_id FK
        uuid product_variant_id FK "nullable, UNUSED"
        int line_number "UK with version"
        uuid source_line_id FK "nullable, self"
        numeric quantity "CHECK > 0"
        numeric unit_list_price "CHECK >= 0"
        numeric unit_cost "CHECK >= 0, server-set"
        numeric discount_pct "CHECK 0..100"
        numeric net_amount
        numeric line_cost
        numeric line_margin
        numeric line_margin_pct
    }
    POLICY_RESULTS {
        uuid id PK
        uuid quote_version_id FK
        uuid quote_line_id FK "nullable"
        varchar64 rule
        varchar48 status "PASSED|WARNING|VIOLATED|NOT_APPLICABLE"
        numeric actual_value
        numeric threshold_value
        numeric overage_points
        text reason "NOT NULL - never a bare number"
        numeric risk_contribution
        jsonb detail
    }
    APPROVAL_REQUESTS {
        uuid id PK
        uuid quote_version_id FK "partial UK where status=PENDING"
        varchar48 status "ApprovalRequestStatus"
        uuid requested_by_user_id FK
        jsonb required_levels
        jsonb policy_summary
        numeric blended_risk_score
        int current_step_sequence
        timestamptz stale_at "nullable"
        text stale_reason "nullable"
        uuid superseded_by_request_id FK "nullable, self"
    }
    APPROVAL_STEPS {
        uuid id PK
        uuid approval_request_id FK
        int sequence "UK with request, CHECK >= 1"
        varchar48 level "SALES_MANAGER|FINANCE|EXECUTIVE"
        varchar48 required_role "RoleCode"
        varchar48 status "ApprovalStepStatus"
        uuid decided_by_user_id FK "nullable"
    }
    APPROVAL_DECISIONS {
        uuid id PK
        uuid approval_step_id FK
        varchar48 decision "APPROVE|REJECT|REQUEST_REVISION"
        uuid actor_user_id FK
        varchar48 actor_role
        varchar255 actor_email
        text reason "NOT NULL"
        jsonb decision_snapshot "the numbers they saw"
        timestamptz decided_at
    }
    DECISION_IMPACTS {
        uuid id PK
        uuid quote_version_id FK
        uuid previous_version_id FK "nullable"
        varchar64 changed_field
        jsonb old_value "nullable"
        jsonb new_value "nullable"
        bool material
        varchar48 severity
        text change_reason
    }
    NEGOTIATION_MESSAGES {
        uuid id PK
        uuid thread_id FK
        varchar48 author_kind "CUSTOMER|SELLER|SYSTEM"
        varchar48 message_type "NegotiationMessageType"
        text body
        numeric requested_discount_pct "nullable, CHECK 0..100"
        numeric requested_quantity "nullable, CHECK > 0"
        jsonb payload
    }
```

---

## 5. Entity relationship diagram — execution and billing

```mermaid
erDiagram
    QUOTE_VERSIONS ||--|| SALES_ORDERS : "UNIQUE one order ever"
    SALES_ORDERS ||--o{ SALES_ORDER_LINES : lines
    QUOTE_LINES ||--o{ SALES_ORDER_LINES : "copied from"
    SALES_ORDER_LINES ||--o{ INVENTORY_ALLOCATIONS : reserves
    WAREHOUSES ||--o{ INVENTORY : stocks
    PRODUCTS ||--o{ INVENTORY : "stocked as"
    INVENTORY |o--o{ INVENTORY_ALLOCATIONS : "drawn from"
    WAREHOUSES |o--o{ INVENTORY_ALLOCATIONS : "sourced from"
    SALES_ORDERS ||--o{ FULFILLMENTS : ships
    WAREHOUSES ||--o{ FULFILLMENTS : "ships from"
    FULFILLMENTS |o--o{ INVENTORY_ALLOCATIONS : fulfils
    SALES_ORDER_LINES ||--o{ BILLING_SCHEDULES : bills
    BILLING_SCHEDULES |o--o{ INVOICES : invoiced
    INVOICES ||--o{ PAYMENTS : settled

    SALES_ORDERS {
        uuid id PK
        varchar64 order_number "UK per org"
        uuid quote_version_id FK "UNIQUE - the duplicate-order backstop"
        uuid customer_organization_id FK
        varchar48 status "SalesOrderStatus"
        numeric subtotal
        numeric total_amount
        numeric total_cost
        numeric margin
        numeric one_time_amount
        numeric recurring_amount
        uuid confirmed_by_user_id FK
        bool fully_allocated
        bool has_backorder
    }
    SALES_ORDER_LINES {
        uuid id PK
        uuid sales_order_id FK
        uuid quote_line_id FK
        int line_number "UK with order"
        numeric quantity "CHECK > 0"
        numeric quantity_allocated "CHECK 0..quantity"
        numeric quantity_backordered "CHECK >= 0"
        numeric quantity_fulfilled "CHECK 0..quantity"
    }
    WAREHOUSES {
        uuid id PK
        varchar64 code "UK per org"
        int priority "100"
        numeric shipping_cost_per_shipment "CHECK >= 0"
        bool is_active
    }
    INVENTORY {
        uuid id PK
        uuid warehouse_id FK "UK with product"
        uuid product_id FK
        numeric quantity_on_hand "CHECK >= 0"
        numeric quantity_reserved "CHECK >= 0 AND <= on_hand"
        numeric quantity_inbound
        numeric reorder_point
        timestamptz expected_restock_at "nullable"
    }
    INVENTORY_ALLOCATIONS {
        uuid id PK
        uuid sales_order_line_id FK
        uuid warehouse_id FK "NULL only when BACKORDERED"
        numeric quantity "CHECK > 0"
        varchar48 status "AllocationStatus"
        varchar48 mode "AUTOMATIC|MANUAL_OVERRIDE"
        timestamptz expected_available_at "nullable"
    }
    FULFILLMENTS {
        uuid id PK
        varchar64 fulfillment_number "UK per org"
        uuid warehouse_id FK
        int shipment_sequence
        varchar48 status "FulfillmentStatus"
        varchar128 carrier "nullable"
        varchar128 tracking_number "nullable"
        numeric shipping_cost
    }
    BILLING_SCHEDULES {
        uuid id PK
        varchar64 schedule_number "UK per org"
        uuid sales_order_line_id FK "nullable"
        varchar48 billing_type "ONE_TIME|RECURRING"
        varchar48 recurring_interval "nullable, CHECK paired"
        varchar48 status "BillingScheduleStatus"
        numeric amount "CHECK >= 0"
        int period_number "CHECK >= 1"
        int total_periods "CHECK >= 1"
        date period_start
        date period_end
        date due_date
        bool is_prorated
        numeric proration_factor "NUMERIC(12,8)"
    }
    INVOICES {
        uuid id PK
        varchar64 invoice_number "UK per org"
        uuid billing_schedule_id FK "nullable"
        varchar48 status "InvoiceStatus"
        numeric total_amount
        numeric amount_paid "CHECK 0..total_amount"
        date issue_date
        date due_date
    }
    PAYMENTS {
        uuid id PK
        varchar64 payment_number "UK per org"
        uuid invoice_id FK
        numeric amount "CHECK > 0"
        varchar48 method "PaymentMethod"
        varchar48 status "PaymentStatus"
        uuid recorded_by_user_id FK "nullable"
    }
```

---

## 6. System tables

```mermaid
erDiagram
    ORGANIZATIONS |o--o{ AUDIT_EVENTS : scopes
    USERS |o--o{ AUDIT_EVENTS : "actor on"
    ORGANIZATIONS ||--o{ ATTENTION_ITEMS : scopes
    DEALS |o--o{ ATTENTION_ITEMS : flags
    QUOTES |o--o{ ATTENTION_ITEMS : flags
    ORGANIZATIONS ||--o{ IDEMPOTENCY_KEYS : scopes

    AUDIT_EVENTS {
        uuid id PK
        bigint sequence UK "IDENTITY - stable total order"
        uuid organization_id FK "nullable, SET NULL"
        varchar64 event_type
        varchar64 entity_type
        uuid entity_id "nullable, no FK - polymorphic"
        uuid actor_user_id FK "nullable"
        varchar48 actor_role "nullable"
        varchar255 actor_email "nullable"
        jsonb payload "money as strings"
        varchar64 ip_address "nullable"
        timestamptz occurred_at
    }
    ATTENTION_ITEMS {
        uuid id PK
        varchar64 source_type
        uuid source_id "no FK - polymorphic"
        varchar48 type "AttentionItemType"
        varchar48 severity "Severity"
        varchar255 title
        text reason "why"
        text impact "what it costs"
        varchar48 owner_role "who"
        text recommended_action "what next"
        varchar48 status "OPEN|ACKNOWLEDGED|RESOLVED"
        jsonb detail
    }
    IDEMPOTENCY_KEYS {
        uuid id PK
        varchar128 key "UK with org+endpoint"
        varchar255 endpoint
        varchar128 request_hash "SHA-256 of canonical body"
        varchar48 status "IN_PROGRESS|COMPLETED|FAILED"
        int response_status_code "nullable"
        jsonb response_body "nullable - replayed verbatim"
        timestamptz expires_at "nullable, indexed"
    }
```

`audit_events` has **no `updated_at`** — it uses `CreatedAtMixin`. There is
structurally nothing to rewrite history with. Its `organization_id` is nullable
with `ON DELETE SET NULL` so the trail outlives the tenant.

---

## 7. Constraint inventory that enforces business rules

The database is the last line of defence. These constraints mean an application
bug produces a failed transaction, not corrupt commercial data.

| Constraint | Table | Guarantees |
|---|---|---|
| `UNIQUE (quote_version_id)` | `sales_orders` | **One order per quote version, ever.** The duplicate-confirmation backstop above the idempotency layer. |
| `CHECK (quantity_reserved <= quantity_on_hand)` | `inventory` | **Inventory can never be over-allocated**, even with a bug in `InventoryService`. |
| Partial `UNIQUE (quote_version_id) WHERE status='PENDING'` | `approval_requests` | At most one open approval per version. |
| Partial `UNIQUE (org, source_type, source_id, type) WHERE status<>'RESOLVED'` | `attention_items` | One live item per source, so re-evaluation refreshes rather than spams the Control Tower. |
| `CHECK ((status='BACKORDERED' AND warehouse_id IS NULL) OR (status<>'BACKORDERED' AND warehouse_id IS NOT NULL))` | `inventory_allocations` | A backorder has no warehouse; a reservation always does. |
| `CHECK ((billing_type='RECURRING' AND recurring_interval IS NOT NULL) OR (billing_type='ONE_TIME' AND recurring_interval IS NULL))` | `billing_schedules` | Recurring implies an interval. |
| `CHECK (quantity_allocated >= 0 AND <= quantity)` | `sales_order_lines` | Cannot allocate more than ordered. |
| `CHECK (quantity_fulfilled >= 0 AND <= quantity)` | `sales_order_lines` | Cannot ship more than ordered. |
| `CHECK (amount_paid >= 0 AND <= total_amount)` | `invoices` | No overpayment at the storage layer. |
| `CHECK (discount_pct >= 0 AND <= 100)` | `quote_lines` | Discount is a real percentage. |
| `CHECK (quantity > 0)` | `quote_lines`, `sales_order_lines`, `inventory_allocations` | No zero or negative line. |
| `CHECK (version_number >= 1)` | `quote_versions` | Versions start at 1. |
| `UNIQUE (quote_id, version_number)` | `quote_versions` | No duplicate version numbers. |
| `UNIQUE (quote_version_id, line_number)` | `quote_lines` | Stable line numbering. |
| `UNIQUE (approval_request_id, sequence)` | `approval_steps` | Ordered steps, no ties. |
| `UNIQUE (warehouse_id, product_id)` | `inventory` | One stock row per pair. |
| `UNIQUE (organization_id, <natural key>)` | products, policies, warehouses, deals, quotes, orders, price_lists, variants, fulfillments, schedules, payments | Tenant-scoped natural keys. |
| `ON DELETE RESTRICT` | commercial FKs (products, users, profiles on orders) | Cannot delete a product that has been sold. |
| `ON DELETE CASCADE` | version → lines, request → steps, order → lines | Child rows follow their parent. |
| `ON DELETE SET NULL` | self-refs, optional FKs, audit actor | History survives deletion of the referent. |

---

## 8. JSONB payload shapes

17 JSONB columns. Shapes are inferred from the services that write them.

### `commercial_snapshots.snapshot_json`

Written by `CommercialEngine.calculate_version`, then merged with risk data by
`PolicyEngine`. All money and percentage values are **strings**.

```json
{
  "version_number": 1,
  "status": "DRAFT",
  "currency": "USD",
  "line_count": 4,
  "lines": [
    {
      "quote_line_id": "uuid", "product_id": "uuid", "line_number": 1,
      "description": "Business Laptop", "category": "HARDWARE",
      "quantity": "100.0000", "unit_list_price": "1200.0000",
      "unit_cost": "800.0000", "unit_net_price": "984.0000",
      "discount_pct": "18.0000", "gross_amount": "120000.00",
      "discount_amount": "21600.00", "net_amount": "98400.00",
      "tax_amount": "0.00", "total_amount": "98400.00",
      "line_cost": "80000.00", "line_margin": "18400.00",
      "line_margin_pct": "18.6992", "billing_type": "ONE_TIME",
      "recurring_interval": null, "recurring_periods": 1
    }
  ],
  "totals": {
    "gross_revenue": "160800.00", "total_discount": "28090.00",
    "net_revenue": "132710.00", "tax_amount": "0.00",
    "total_revenue": "132710.00", "total_cost": "100200.00",
    "margin": "32510.00", "margin_pct": "24.4970",
    "effective_discount_pct": "17.4689",
    "one_time_revenue": "132410.00", "recurring_revenue": "300.00"
  },
  "blended_risk": { "score": "32.4443", "band": "MEDIUM", "components": [] },
  "policy_violations": [],
  "required_approvals": []
}
```

### `approval_requests.required_levels`

```json
[
  { "type": "SALES_MANAGER", "reason": "...", "triggered_by": ["CATEGORY_DISCOUNT_CEILING"] },
  { "type": "FINANCE", "reason": "...", "triggered_by": ["DISCOUNT-AUTHORITY-20K"] }
]
```

### `approval_requests.policy_summary`

```json
{
  "violation_count": 3,
  "blended_risk": { "score": "32.4443", "band": "MEDIUM", "components": [], "formula": "...", "explanation": "..." },
  "required_approvals": [],
  "violations": []
}
```

### `approval_decisions.decision_snapshot`

The numbers the approver was actually looking at.

```json
{
  "version_number": 1, "total_revenue": "132710.00", "net_revenue": "132710.00",
  "total_cost": "100200.00", "margin": "32510.00", "margin_pct": "24.4970",
  "total_discount": "28090.00", "blended_risk_score": "32.4443", "risk_band": "MEDIUM"
}
```

### `policy_results.detail`

Varies by rule. Examples: `{"line_number": 3}`,
`{"policy_code": "GOLD-SV-CEILING"}`,
`{"margin_amount": "32510.00", "net_revenue": "132710.00"}`.

### `negotiation_messages.payload`

For `COUNTER_OFFER` / `CHANGE_REQUEST`:

```json
{
  "requested_lines": [
    {
      "quote_line_id": "uuid", "description": "Business Laptop",
      "current_discount_pct": "18.0000", "requested_discount_pct": "25.0000",
      "current_quantity": "100.0000", "requested_quantity": null
    }
  ]
}
```

### `decision_impacts.old_value` / `new_value`

Arbitrary JSON scalars for field-level diffs: `"18.0000"` → `"25.0000"`,
or `null` when a line was added or removed.

### `attention_items.detail`

Context for deep-linking: `quote_version_id`, `message_id`, `new_version_id`,
`shortfall`, margin violation figures.

### `billing_schedules.detail`

`{"quantity": "1.0000", "unit_net_price": "300.0000", "category": "SUBSCRIPTION", "interval_months": 12}`

### `audit_events.payload`

Event-specific. Keys prefixed with `_` (`_actor_email`, `_actor_role`,
`_ip_address`) are consumed by the audit writer and **stripped** from the stored
payload. Money is always a string.

### `product_variants.attributes` · `price_lists.rules` · `policies.config` · `idempotency_keys.response_body`

| Column | Shape |
|---|---|
| `product_variants.attributes` | Free-form, e.g. `{"size": "15-inch", "pack": 1}` |
| `price_lists.rules` | `[{"product_id": "uuid", "unit_price": "1100.00"}]` — **written but never read** |
| `policies.config` | Extensible dict, default `{}`; no fixed schema |
| `idempotency_keys.response_body` | The full cached HTTP response body, replayed verbatim |

---

## 9. Table inventory

| # | Table | Group | Mixins | Notes |
|---|---|---|---|---|
| 1 | `organizations` | Identity | UUID + Timestamp | No `organization_id`; `kind` SELLER/CUSTOMER |
| 2 | `roles` | Identity | UUID + Timestamp | Global, not tenant-scoped |
| 3 | `users` | Identity | UUID + OrgOwned + Timestamp | `email` globally unique |
| 4 | `contacts` | Identity | UUID + OrgOwned + Timestamp | Unique `(org, email)` |
| 5 | `customer_profiles` | Commercial | UUID + OrgOwned + Timestamp | Bridges seller org ↔ buyer org |
| 6 | `products` | Commercial | UUID + OrgOwned + Timestamp | |
| 7 | `product_variants` | Commercial | UUID + OrgOwned + Timestamp | Not usable in quoting |
| 8 | `price_lists` | Commercial | UUID + OrgOwned + Timestamp | Inert |
| 9 | `deals` | Commercial | UUID + OrgOwned + Timestamp | |
| 10 | `quotes` | Quotes | UUID + OrgOwned + Timestamp | `current_version_number` is an int, not an FK, to avoid a circular FK |
| 11 | `quote_versions` | Quotes | UUID + OrgOwned + Timestamp | Self-FK `parent_version_id` |
| 12 | `quote_lines` | Quotes | UUID + OrgOwned + Timestamp | Self-FK `source_line_id` |
| 13 | `policies` | Governance | UUID + OrgOwned + Timestamp | |
| 14 | `policy_results` | Governance | UUID + OrgOwned + Timestamp | `reason` is NOT NULL |
| 15 | `commercial_snapshots` | Governance | UUID + OrgOwned + Timestamp | One `is_current` per version |
| 16 | `approval_requests` | Approvals | UUID + OrgOwned + Timestamp | Self-FK `superseded_by_request_id` |
| 17 | `approval_steps` | Approvals | UUID + OrgOwned + Timestamp | |
| 18 | `approval_decisions` | Approvals | UUID + OrgOwned + **CreatedAt** | Append-only |
| 19 | `decision_impacts` | Tracking | UUID + OrgOwned + **CreatedAt** | Append-only; stores non-material diffs too |
| 20 | `attention_items` | Tracking | UUID + OrgOwned + Timestamp | Polymorphic `source_id` |
| 21 | `negotiation_threads` | Negotiation | UUID + OrgOwned + Timestamp | Unique on `quote_id` |
| 22 | `negotiation_messages` | Negotiation | UUID + OrgOwned + **CreatedAt** | Append-only |
| 23 | `sales_orders` | Execution | UUID + OrgOwned + Timestamp | Unique `quote_version_id` |
| 24 | `sales_order_lines` | Execution | UUID + OrgOwned + Timestamp | |
| 25 | `fulfillments` | Execution | UUID + OrgOwned + Timestamp | One per warehouse |
| 26 | `warehouses` | Inventory | UUID + OrgOwned + Timestamp | |
| 27 | `inventory` | Inventory | UUID + OrgOwned + Timestamp | Unique `(warehouse, product)` |
| 28 | `inventory_allocations` | Inventory | UUID + OrgOwned + Timestamp | |
| 29 | `billing_schedules` | Billing | UUID + OrgOwned + Timestamp | |
| 30 | `invoices` | Billing | UUID + OrgOwned + Timestamp | |
| 31 | `payments` | Billing | UUID + OrgOwned + Timestamp | |
| 32 | `audit_events` | System | UUID + **CreatedAt** | **Not** OrgOwned — nullable org, SET NULL |
| 33 | `idempotency_keys` | System | UUID + OrgOwned + Timestamp | |

---

## 10. Computed properties (no DB column)

| Model | Property | Expression |
|---|---|---|
| `Organization` | `is_seller` | `kind == SELLER` |
| `User` | `role_code`, `is_internal` | from joined `Role` |
| `Contact` | `display_name` | first + last name |
| `CustomerProfile` | `credit_available` | `credit_limit - credit_used` |
| `CustomerProfile` | `payment_terms_days` | `PaymentTerms` → int |
| `Product` | `unit_margin` | `list_price - internal_cost` |
| `Policy` | `specificity` | score from scope columns; most specific policy wins |
| `QuoteVersion` | `is_editable` | `status in {DRAFT}` |
| `QuoteVersion` | `is_revisable` | `status in REVISABLE_VERSION_STATUSES` |
| `QuoteVersion` | `is_terminal` | `status in {CONFIRMED, REJECTED, SUPERSEDED}` |
| `ApprovalRequest` / `ApprovalStep` | `is_open` | `status == PENDING` |
| `Inventory` | `quantity_available` | `quantity_on_hand - quantity_reserved` |
| `SalesOrderLine` | `quantity_outstanding` | `quantity - quantity_allocated` |
| `Invoice` | `amount_due` | `total_amount - amount_paid` |

No `hybrid_property` and no `@validates` hooks exist. Only 8 `relationship()`
definitions exist, all unidirectional with no cascade — loading is explicit,
which keeps async query behaviour predictable.

---

## 11. Data model gaps

| # | Gap | Impact | Priority |
|---|---|---|---|
| 1 | No `sales_teams` table | PDF A7's "Sales Team / Rep" report filter has nothing to filter on | P0 |
| 2 | No `credit_notes` table | PDF A5/B7 partial refund and credit note cannot be represented | P0 |
| 3 | No per-organization settings table | PDF A3 approval chain and B9 stalled window must be configurable per tenant; both are currently process-global | P0 |
| 4 | No rep discount baseline storage | PDF B9 anomaly detection needs a rolling per-rep average | P0 |
| 5 | No delivery promise date on orders or fulfillments | PDF B9 slippage indicator has nothing to measure against | P0 |
| 6 | No order-level discount column on `quote_versions` | PDF B3 requires line **or order** level discounts | P0 |
| 7 | `quote_lines.product_variant_id` unreachable | `QuoteLineCreate` has no such field, so variants can never be attached | P1 |
| 8 | `price_lists.rules` never read | Tier pricing is inert | P1 |
| 9 | No `is_promoted` on products | PDF B5 promotion tag cannot be rendered | P1 |
| 10 | No dismissed-recommendation storage | PDF B5 Dismiss does not persist | P1 |
| 11 | `inventory` unique on `(warehouse, product)` only | Variant-level stock is not modelled, though `product_variant_id` exists on the row | P2 |
| 12 | `idempotency_keys.expires_at` written but never pruned | Table grows without bound | P3 |
