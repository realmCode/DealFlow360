# PROBLEM ANALYSIS

Source of truth: `HackathonMatrials/DealFlow360.pdf` (13 pages).
Supporting reference: `HackathonMatrials/DealFlow360 - End to End Product Flow 24 hours oxp.excalidraw.png`
and the published mockup <https://app.excalidraw.com/l/65VNwvy7c4X/7Fb5SR3WKu2>.

Every requirement below is traced to its PDF section. Where this document draws a
conclusion the PDF does not state outright, it is labelled `INFERRED`.

---

## A. Official problem definition

| Field | Value |
|---|---|
| Problem title | **DealFlow360 — An Intelligent, Self Governing Sales Operations Platform** |
| Organization / ministry | ❌ NOT STATED IN PDF. No ministry, department or sponsoring body is named. |
| Problem ID | ❌ NOT STATED IN PDF. |
| Domain | B2B Sales Operations / CPQ (Configure-Price-Quote) to Cash |
| Page count | 13 |

### Official problem statement (PDF §1, verbatim intent)

DealFlow360 is a Sales Operations platform designed to handle:

1. Multi-tier discount governance and automated approval routing
2. Live upsell and cross-sell recommendations while building a quotation
3. Multi-warehouse fulfillment splitting and backorder handling
4. Hybrid billing (one-time products mixed with recurring subscription lines)
5. Deal health monitoring and anomaly alerts
6. Customer-facing portal negotiation on live quotations
7. Sales backend configuration and reporting dashboards

The PDF frames the problem as a deliberate rejection of naive CRUD:

> "Most simple sales tools handle the basics well: create a quote, confirm an
> order, invoice it. Real B2B sales teams operate in messier conditions such as
> multi level discount approvals, partial stock spread across warehouses,
> bundled subscriptions mixed with one time hardware, customers who want to
> negotiate inside a portal instead of over email, and managers who only find
> out a deal is stuck after it has already lost momentum."

And states the intended outcome:

> "...becomes a self governing deal engine, one that enforces pricing
> discipline, reacts to inventory reality in real time, keeps subscriptions and
> one time sales reconciled on a single order, and gives both sales reps and
> customers a living, negotiable document instead of a static PDF."

**The operative phrase is "self governing."** The system must enforce policy
without a human remembering to ask. This is the axis the whole solution is
judged on.

### Main goal (PDF §2)

> "Build a complete sales flow including backend configuration and a frontend
> quotation to cash experience."

Note the two halves: **backend configuration area** and **frontend rep
workspace**. A solution that only builds the rep workspace has skipped half the
stated goal.

### Key outcomes (PDF §2) — the six acceptance statements

| # | Outcome |
|---|---|
| KO1 | Sales rep can log in, build a quotation, and have it **auto route** for the correct approval based on discount and customer tier |
| KO2 | Rep receives **live** upsell and cross-sell suggestions with **real-time margin impact** while building the quote |
| KO3 | Order can be **automatically split across warehouses** based on stock availability, **with manual override** |
| KO4 | A single order can **mix one-time products and recurring subscription lines** with correct **proration** and billing schedules |
| KO5 | Dashboard shows **deal health, stalled quotes, and discount anomalies** in real time |
| KO6 | Customer can **view and negotiate** the quotation directly from a customer-facing portal **without email back and forth** |

### Constraints (PDF §7 "Technical Guidelines")

| Constraint | Consequence |
|---|---|
| Any language, framework, or database permitted | No stack penalty. Python/FastAPI/PostgreSQL is fully compliant. |
| **Core business rules must be implemented in application logic, not hardcoded or faked for the demo** | Hard constraint. Approval routing, discount governance, warehouse splitting and billing proration must be computed, not scripted. |
| **The customer-facing negotiation screen must be a real, separate, restricted view — not just another internal screen with a different label** | Hard constraint. Requires genuine authorization separation and data redaction. |
| Multi-currency / multi-company support is a **bonus, not a requirement** | Do not spend budget here. |

### Deliverables (PDF §8)

| # | Deliverable | Status in this project |
|---|---|---|
| D1 | A working application (**backend plus frontend**) with sample seed data | Backend + deterministic seed complete; frontend pending |
| D2 | A **five-minute live demo** covering **at least two full flows** end to end, from quotation to fulfillment or billing | Feasible; canonical flow + clean auto-approve flow are the two |
| D3 | A **one-page architecture diagram** showing the data model and how the major modules connect | To be produced in `SYSTEM_ARCHITECTURE.md` |
| D4 | A short note on **what the team would build next** with more time | Exists as README §25; to be consolidated |

### Target beneficiaries and stakeholders (PDF §3)

- **Primary beneficiary:** the sales representative, who currently loses deals to
  process friction rather than to competitors.
- **Secondary beneficiary:** the sales manager and finance approver, who under the
  status quo "only find out a deal is stuck after it has already lost momentum."
- **External stakeholder:** the customer, who under the status quo negotiates over
  email against a static PDF.
- **Organizational stakeholder:** the business, whose margin erodes invisibly when
  every line is technically within limits but the order as a whole is over-discounted.

### Existing pain points named or clearly implied by the PDF

| Pain point | PDF evidence |
|---|---|
| Discount approval is manual and inconsistently applied | §2 KO1 "**without the rep having to request it manually**" (§9 step 3) |
| A single overall discount limit hides per-category abuse | §10 "the system checks every line against **its own limit**, not just one overall limit" |
| Many small violations evade review | §10 "none of them look alarming alone, but added together across the order, the rep has quietly given away a lot of margin" |
| Managers review every quote by hand | §10 "so managers are not stuck reviewing every single quotation by hand" |
| Stock reality is invisible at quote time | §1 "partial stock spread across warehouses" |
| Subscriptions and hardware are reconciled in separate systems | §1 "bundled subscriptions mixed with one time hardware" |
| Negotiation happens over email against a dead document | §1 "customers who want to negotiate inside a portal instead of over email"; "living, negotiable document instead of a static PDF" |
| Deal decay is discovered too late | §1 "managers who only find out a deal is stuck after it has already lost momentum" |

### Expected outcomes (PDF §6)

- Demonstrates a complete real-world B2B workflow: Quotation → Approval →
  Fulfillment → Billing → Customer Negotiation → Reporting.
- Focuses on **business logic**, not UI screens.
- Demonstrates **industry-ready system thinking**: role-based access, approval
  chains, inventory coordination, recurring billing, audit trails, deal analytics.

---

## B. Module requirements, verbatim structure

The PDF specifies two lettered module groups. This structure is used as the
primary traceability key throughout the documentation set.

### Group A — Sales Backend (Configuration Area)

| ID | Module | Requirements |
|---|---|---|
| **A1** | Authentication (Login / Signup) | Internal users sign up and log in with standard credentials. Customers access quotations through a portal login (**magic link, or email and password**). After login, internal users can access backend configuration and open a sales workspace. |
| **A2** | Product & Price List Management | **General info:** name, category, price, unit, tax, description. **Variants:** attribute (e.g. Size or Pack), values, extra prices. **Price lists:** customer-tier-based pricing, currency-specific rules. |
| **A3** | Discount Tier & Approval Chain Setup | Discount ceilings **per customer tier** (Bronze ≤5%, Silver ≤10%, Gold ≤15%). **Category-specific** ceilings. Configure approval chain: which discount range needs Sales Manager only, which needs Sales Manager **then** Finance. When a quote mixes categories with different ceilings, compute a **blended risk score** and route to the **highest required level**. All approvals, rejections and edits logged with **user, timestamp and reason**. |
| **A4** | Warehouse & Fulfillment Setup | Create and manage warehouses. Configure **stock levels and replenishment rules** per warehouse. Define **shipping cost weighting** used by auto-split logic to minimize shipment count. |
| **A5** | Subscription / Recurring Plan Setup | Define recurring plans (**monthly, quarterly, yearly**) attachable to products or services. Configure **proration rules for mid-cycle quantity or plan changes**. Configure **cancellation and partial refund rules**. |
| **A6** | Upsell / Cross-Sell Rule Setup **(marked OPTIONAL)** | Product pairings from **historical co-purchase data**. Mark products as **promoted** so they rank higher. Set **minimum margin thresholds** so only healthy-margin suggestions surface. |
| **A7** | Reporting & Dashboard Configuration | Dashboard plus reporting menu for sales performance. **Export: PDF / XLS.** Filters: **Period** (today, week, custom range), **Sales Team / Rep**, **Approval Status** (pending/approved/rejected), **Product / Category** (best-selling, most-discounted). |

### Group B — Sales Frontend (Rep Workspace Experience)

| ID | Screen | Requirements |
|---|---|---|
| **B1** | Sales Workspace Top Menu | Nav: **Quotations** (list of active and draft quotations), **Pipeline** (Kanban-style deal pipeline). Actions: **Reload Data** (refresh pricing, stock, approval data), **Go to Back-end**, **Close Workspace**. |
| **B2** | Quotation List / Pipeline View | Quotations as **selectable cards showing customer, amount, and stage**. Examples: "Acme Corp, Draft", "Beta Industries, Pending Approval". Selecting opens the Quotation Builder. |
| **B3** | Quotation Builder (Products + Cart) | Pick products across categories (Hardware, Services, Subscriptions). Adjust quantities (+/−). Apply **line-level or order-level discounts**. View order lines with totals and a **live margin indicator**. Confirm and move to approval, **or straight to fulfillment if no approval is required**. |
| **B4** | Discount Approval Screen | **Blended risk score.** Approval steps list: Sales Manager, and Finance (**only shown when required**). Each reviewer can **Approve, Reject, or Return for revision**. Confirmation screen with a **full audit trail entry**. |
| **B5** | Upsell / Cross-Sell Panel (**Special Flow**) | Shown **alongside the cart**. Ranked suggestions from co-purchase history and active promotions. Displays: suggested product, **margin delta if added**, **promotion tag**. Buttons: **Add to Quote**, **Dismiss**. After adding, the **margin indicator updates immediately**. |
| **B6** | Fulfillment & Warehouse Split | Recommended split based on **live stock**. Displays warehouse name, quantity from that warehouse, **estimated shipment count and cost**. Buttons: **Accept Suggested Split**, **Manual Override**. If stock arrives mid-fulfillment, a **"Consolidate Remaining Backorder" prompt appears automatically**. |
| **B7** | Subscription & Billing Screen | One-time and recurring lines shown **separately within the same order**. Upcoming billing schedule for recurring lines. **Mid-cycle proration when quantity changes.** **Cancel or modify subscription controls, with automatic partial refund or credit note trigger.** |
| **B8** | Customer Portal Negotiation | **Separate from the internal workspace.** Shows quotation details and status (Sent, Under Negotiation, Confirmed). **Line-level comment and change request tool.** **Counter discount proposal field.** Buttons: Submit Request, Confirm Quotation. After confirmation: if final terms exceed thresholds the quote **automatically re-enters the approval flow from B4**; otherwise the order moves directly to fulfillment. |
| **B9** | Deal Health & Anomaly Dashboard | **Stalled deals** (inactive more than a **configured number of days**). **Discount anomaly alerts** (a discount **well above a rep's historical average**). **Delivery promise slippage indicators.** Clicking an alert opens the related quotation. **An automated nudge or escalation action can be triggered from an alert.** |

---

## C. The Quick Test Flow — treat as the scoring script

PDF §9 provides an eight-step walkthrough with an explicit pass condition:

> "If all eight steps work smoothly and each result matches what is expected,
> the core flow is solid."

`INFERRED` — this is the highest-value artifact in the PDF. It is almost
certainly what a judge will run. Every step must be demonstrable without
apology.

| Step | Requirement | Notes |
|---|---|---|
| QT1 | Sign up or log in, and set up basic backend data: **a discount tier, a warehouse, and a subscription plan** | Exercises A1, A3, A4, A5 |
| QT2 | Create a quotation and add a product line with **a discount higher than what is normally allowed** | Exercises A2, A3, B3 |
| QT3 | Confirm the quotation **automatically asks for manager approval, without the rep having to request it manually** | The self-governing claim. Exercises A3, B4 |
| QT4 | While building the quote, **accept one upsell suggestion** and confirm **the order total and margin update right away** | Exercises A6, B5. Requires the suggestion to be addable and the recalculation to be immediate |
| QT5 | Get the quotation approved, then confirm stock is pulled from the **correct warehouse, splitting across two warehouses if needed** | Exercises A4, B6 |
| QT6 | Check that a **one-time product and a recurring subscription on the same order are billed correctly and separately** | Exercises A5, B7 |
| QT7 | Open the **customer portal** view and **request a bigger discount as the customer**, then confirm the quote **goes back for approval automatically** | The differentiating loop. Exercises B8 → B4 |
| QT8 | **Confirm the order, record a payment, and check that the invoice status updates correctly** | Exercises B7. Requires invoices and payments to be real, not stubs |

---

## D. Understanding the blended discount risk score (PDF §10)

The PDF dedicates a full section to this, which signals it is the intellectual
centre of the problem. Reproduced faithfully:

**The simple framing.** "Different products are allowed different discount
limits, and the system checks every line against its own limit, not just one
overall limit for the whole order."

**Worked example from the PDF.** A Gold customer is normally allowed up to 15%.
Within the same order, hardware is allowed up to 15% (healthy margins) and
services only up to 10% (thin margins).

- Laptop (Hardware): 12% given, 15% allowed → line is fine
- Setup Service (Service): 18% given, 10% allowed → **8 points over its limit**

> "Even though the customer is Gold and 15 percent sounds fine on paper, the
> Service line broke its own stricter limit. So the whole quotation gets flagged
> for approval, because of that one line."

**Why "blended".**

> "Sometimes no single line is badly over its limit, but many lines are each a
> little over. One line 2 points over, another 3 points over, another 2 points
> over. None of them look alarming alone, but added together across the order,
> the rep has quietly given away a lot of margin. The blended score looks at the
> total pattern across the order, not just the single worst line, so small
> violations spread across many lines cannot slip through unnoticed."

**Why it matters.**

1. "It decides who needs to review the deal before it is approved, so managers
   are not stuck reviewing every single quotation by hand."
2. "It stops a rep from keeping every line technically within limits while still
   discounting the order more than the company intends overall."

### What this section demands of an implementation

| Demand | Implication |
|---|---|
| Per-line evaluation against a **line-specific** ceiling | Ceilings must be resolvable by (customer tier × product category), not a single scalar |
| A **single order-level score** aggregating all breaches | Not `max()` of violations — an additive/aggregate measure |
| **Breadth sensitivity** — many small violations must accumulate | The score must have a term that grows with violation *count*, not just depth |
| **Total-giveaway sensitivity** | The score must react to overall discount depth even when every line is compliant (requirement 2 of "why it matters") |
| **Routing derived from the score and the breached rules** | Route to the *highest required level*, not a fixed chain |
| Explainability | A bare number cannot satisfy "decides who needs to review" defensibly; the reason must be inspectable |

`INFERRED` — revenue-weighting is not named in the PDF, but it is the only way
to honour the second "why it matters" clause without producing absurd results:
without it, 8 points over on a $410 service line would outrank 3 points over on
$98,400 of hardware, which inverts the actual margin exposure. The existing
implementation weights by revenue share, which is defensible and should be
documented as a deliberate design decision rather than an unstated assumption.

---

## E. Hidden product requirements

The PDF describes screens and rules. It does not describe what happens when
reality intrudes. These are the questions a judge looking for flaws will ask.

### Who is in the loop

| Question | Answer for this problem |
|---|---|
| Who experiences the problem? | The rep (friction), the manager (blind spots), the business (margin leak), the customer (email ping-pong) |
| Who creates data? | Admin creates configuration; Rep creates deals, quotes, lines; Customer creates negotiation messages and counter-offers; Ops creates allocations and fulfillments; Finance creates invoices and payments |
| Who consumes data? | Rep (quote state, stock, approval status), Manager (deal health, approval queue), Finance (risk, margin, billing), Ops (allocation), Customer (redacted quote), Admin (analytics) |
| Who verifies data? | Manager verifies discount justification; Finance verifies margin and signing authority; Ops verifies stock reality |
| Who approves actions? | Manager (SALES_MANAGER level), Finance (FINANCE level), Admin (escalation/break-glass) |
| Who manages the system? | Admin (catalog, tiers, chains, warehouses, plans, thresholds) |
| Who is accountable? | The approver of record on the version that became the order. This makes an immutable, actor-attributed audit trail a **requirement, not a nicety** |

### What happens when reality intrudes

| Scenario | Required behaviour | PDF anchor |
|---|---|---|
| A rep mistypes a discount | Validation rejects out-of-range values; a corrected value re-runs governance | §7 "not hardcoded or faked" |
| **A quote is approved, then the terms change** | The prior approval must **not** silently authorise the new terms. This is the deepest requirement in the document and is only implied — §5 says "If terms change beyond thresholds during negotiation, the quote **re enters the approval flow automatically**" | §5, B8 |
| Two approvers act at once | One decision wins; the other is told the step is already decided | `INFERRED` |
| Two orders race for the last unit of stock | Stock cannot go negative or be double-promised | §1 "reacts to inventory reality in real time" |
| A customer double-clicks Confirm | Exactly one order exists | `INFERRED` — but essential; duplicate orders are an obvious judge probe |
| A rep refreshes mid-build | Server state is authoritative; no client-held totals | §7 "business logic in application logic" |
| A customer tries to read another customer's quote | Denied, and the denial must not confirm the record exists | §7 "real, separate, restricted view" |
| An internal user opens the portal endpoint | Denied — otherwise the redacted view becomes an alias for the internal one | §7, explicit |
| Stock arrives while an order is backordered | A consolidation path must exist | B6, explicit |
| A subscription quantity changes mid-cycle | Proration must be applied, not just previewed | A5, B7, explicit |
| A subscription is cancelled | Partial refund or credit note must be triggered | A5, B7, explicit |
| A deal goes quiet | It must surface as stalled after a **configured** window | B9, explicit |
| A rep's discounting drifts upward over time | It must surface as an anomaly **relative to that rep's own history** | B9, explicit |
| A delivery promise is going to be missed | It must surface as slippage | B9, explicit |
| An alert is raised and ignored | A **nudge or escalation** must be actionable from the alert | B9, explicit |

---

## F. Requirement classification

### MANDATORY — the solution is incomplete without these

| ID | Requirement |
|---|---|
| M1 | Internal auth (signup/login) and customer portal auth | A1 |
| M2 | Product management with category, price, unit, tax, description | A2 |
| M3 | Product variants with attributes and extra prices | A2 |
| M4 | Tier-based price lists | A2 |
| M5 | Per-tier and per-category discount ceilings, configurable | A3 |
| M6 | Configurable approval chain (SM only vs SM then Finance) | A3 |
| M7 | Blended risk score across mixed categories, routing to highest level | A3, §10 |
| M8 | Every approval/rejection/edit logged with user, timestamp, reason | A3 |
| M9 | Warehouse CRUD, stock levels, replenishment rules | A4 |
| M10 | Shipping cost weighting driving shipment minimisation | A4 |
| M11 | Recurring plans (monthly/quarterly/yearly) attachable to products | A5 |
| M12 | Proration applied on mid-cycle quantity or plan change | A5, B7 |
| M13 | Cancellation with partial refund or credit note | A5, B7 |
| M14 | Sales performance reporting with Period/Rep-Team/Approval-Status/Product filters | A7 |
| M15 | PDF and XLS export | A7 |
| M16 | Quotation list and Kanban pipeline with customer, amount, stage | B1, B2 |
| M17 | Quote builder with line-level **and order-level** discounts and live margin | B3 |
| M18 | Approval screen showing blended score, conditional steps, approve/reject/return | B4 |
| M19 | Upsell panel with margin delta, promotion tag, Add to Quote, Dismiss | B5 |
| M20 | Auto warehouse split with manual override and backorder consolidation | B6 |
| M21 | One-time and recurring shown separately on one order with schedule | B7 |
| M22 | Real, separate, restricted customer portal with line comments and counter-offer | B8, §7 |
| M23 | Auto re-entry into approval when negotiated terms exceed thresholds | B8, §5 |
| M24 | Stalled deals with a configurable day threshold | B9 |
| M25 | Discount anomaly vs the rep's historical average | B9 |
| M26 | Delivery promise slippage indicators | B9 |
| M27 | Nudge / escalation action from an alert | B9 |
| M28 | Invoice status updates on payment | QT8 |

### IMPORTANT IMPLIED — not written, but the solution fails a probing judge without them

| ID | Requirement | Rationale |
|---|---|---|
| I1 | **Approval staleness** — a material change invalidates the prior approval and blocks conversion | §5 says the quote re-enters approval; it is meaningless if the old approval still authorises the order |
| I2 | **Quote versioning with immutable history** | "living, negotiable document" plus an audit trail requires prior terms be preserved, not overwritten |
| I3 | **Self-approval prohibition** | An approval chain a rep can satisfy themselves is not governance |
| I4 | **Ordered approval steps** | "Sales Manager **followed by** Finance" is a sequence, not a set |
| I5 | **Tenant / organization isolation** | Multi-company is a bonus, but leaking between seller orgs is a correctness failure |
| I6 | **Idempotent confirmation** | Double-click on Confirm must not create two orders |
| I7 | **Concurrency-safe allocation** | Stock must not be double-promised |
| I8 | **Structural redaction** — cost/margin absent from portal schemas, not merely hidden | §7 demands a real restricted view |
| I9 | **Server-authoritative money** with exact decimal arithmetic | Margin decisions cannot rest on float drift |
| I10 | **Pagination, filtering, sorting on list endpoints** | B2 and A7 are unusable at realistic volume without them |
| I11 | **Deterministic seed data** | D1 requires sample data; a live demo requires it be reproducible |

### OPTIONAL DIFFERENTIATING — earn the "deeper understanding" reaction

| ID | Feature | Rationale |
|---|---|---|
| O1 | **What-if simulation** — evaluate a hypothetical discount without persisting | Turns the risk score from a verdict into a planning tool |
| O2 | **Explainable risk decomposition** — per-component arithmetic with prose | Directly answers §10's demand that the score justify who reviews |
| O3 | **Deal replay / autopsy** from snapshots + audit | Answers "what was true when this was approved?" |
| O4 | **Co-purchase-derived pairings and promoted products** | A6, explicitly optional |
| O5 | **Causal-chain narration** of a governance decision | Makes the self-governing claim legible in a 5-minute demo |

### UNNECESSARY — do not build

| Feature | Reason |
|---|---|
| Multi-currency FX conversion | PDF §7: "a bonus, not a requirement". Cost outweighs credit. |
| Multi-company / multi-tenant onboarding UX | Same clause. Isolation must be correct; onboarding need not exist. |
| Real email or SMS delivery | Nothing in the PDF requires outbound delivery; the portal replaces email by design |
| Payment gateway integration | QT8 requires *recording* a payment and updating invoice status, not processing one |
| Message broker / event streaming infrastructure | In-process events satisfy every stated requirement; Kafka is buzzword cost |
| ML forecasting models | §7 stresses business logic and defensibility; a black box weakens the demo |
| PDF quote generation for customers | The PDF explicitly positions the portal as the replacement for "a static PDF". Export in A7 is for *reports*, not quotes. |
| Mobile native apps | Not mentioned |

---

## G. What "deeper understanding" looks like for this problem

The PDF's own framing points at the winning insight. It says most tools handle
"create a quote, confirm an order, invoice it" and that real teams operate in
"messier conditions." The mess it lists is mostly about **decisions going stale**:

- A discount is approved against numbers that then change.
- Stock is promised from a warehouse that then runs dry.
- A subscription is quoted, then the quantity changes mid-cycle.
- A deal is fine, then goes quiet.

Every one of those is the same failure: **a decision made at time T is still
being trusted at time T+1 after its premises moved.** A solution that detects
premise drift, invalidates the affected decision, re-routes it, and blocks
downstream execution until a human re-decides is answering the actual question.
A solution that merely implements the seven bullet points is answering the
surface question.

This is the thesis the architecture should make obvious.

---

## H. Open items not resolvable from the PDF

| Item | Status |
|---|---|
| Sponsoring organization / ministry | ❌ NOT STATED IN PDF |
| Problem ID | ❌ NOT STATED IN PDF |
| Judging rubric and weightings | ❌ NOT STATED IN PDF |
| Team size or time budget | ❌ NOT STATED IN PDF. The Excalidraw filename says "24 hours", which is the only signal. |
| Required demo dataset scale | ❌ NOT STATED IN PDF |
| Whether magic-link portal auth is preferred over password | PDF offers both as alternatives ("magic link, **or** email and password"); password auth is compliant |
