# REFERENCE_TO_FRONTEND_MAP

Source: `image.png` at the repository root — the Excalidraw board
*"DealFlow360 – End to End Product Flow (Login to Payment)"*, 11908 × 9146,
**18 numbered screens** plus a Navigation Key.

Read at native resolution, screen by screen. The wireframe is treated as
**structure** — screen inventory, navigation model, adjacency, and the business
rules written in its callouts. Its visual styling is not carried over.

---

## The Navigation Key, verbatim

> The white highlighted tab shows which module you are in. Each module has one
> list screen (all records) and one detail screen (one record, opened by
> clicking a row).

| Tab | Opens |
|---|---|
| Dashboard | Screen 2 |
| Quotations | Screen 3 list → Screen 4 detail |
| Approvals | Screen 5 list → Screen 6 detail |
| Fulfillment | Screen 7 list → Screen 8 detail |
| Subscriptions | Screen 9 list → Screen 10 detail |
| Invoices | Screen 12 list → Screen 13 detail |
| Deal Health | Screen 14 |
| Reports | Screen 15 |
| My Quotation / Messages / Profile | Screen 11 (customer portal) |

Two decisions follow, and both are kept:

1. **Navigation is a top tab bar, not a sidebar.** Nine tabs: Dashboard,
   Quotations, Approvals, Fulfillment, Subscriptions, Invoices, Deal Health,
   Reports, Product. A horizontal bar suits a product where you move *between*
   modules constantly, and it returns the full viewport width to dense tables.
   The `--sidebar-width: 240px` from the Data-Dense Dashboard style row is
   therefore dropped in favour of `--header-height: 56px`.
2. **List → detail is the universal pattern.** Every module is a list of all
   records and a detail of one, opened by clicking a row. Consistent, and it
   maps directly onto the backend's collection/resource split.

The customer portal has its own three-tab bar and shares nothing with the
internal chrome — the wireframe already separates them, which matches the
backend's hard redaction boundary.

---

## Screen-by-screen map

| # | Wireframe screen | Route | Backing endpoints | Verdict |
|---|---|---|---|---|
| 1 | Login / Signup | `/login`, `/signup` | `POST /auth/login`, `/auth/signup` | Keep. Split on `is_internal` |
| 2 | Sales Dashboard / Home | `/` | `GET /dashboard/control-tower`, `/attention-items` | **Upgrade** — see below |
| 3 | Quotations (List) — Kanban | `/quotes` | `GET /quotes` | Keep both views |
| 4 | Quotation Detail: Q-1042 | `/quotes/:id` + `…/build` | `/quote-versions/*`, `/policy-results`, `/recommendations` | **Split** into read + build |
| 5 | Approvals (List) | `/approvals` | `GET /approvals/inbox` | Keep |
| 6 | Approval Detail: Q-1042 | `/approvals/:id` | `GET /approvals/{id}` | Keep, extend |
| 7 | Fulfilment and Stock (List) | `/orders` | `GET /orders`, `/inventory` | Keep |
| 8 | Fulfillment Detail: Q-1042 | `/orders/:id` | `POST …/allocate`, `/fulfill` | Keep |
| 9 | Subscriptions (List) | `/billing/subscriptions` | `GET /billing/schedules` | Keep, minus "Paused" |
| 10 | Billing Detail (Care Plan) | `/billing/subscriptions/:id` | `…/change`, `…/cancel`, `/proration-preview` | Keep |
| 11 | Customer Portal Negotiation | `/portal/quotes/:id` | `/portal/quotes/{id}`, `…/messages`, `…/confirm` | Keep, expand to 3 tabs |
| 12 | Invoices (List) | `/billing/invoices` | `GET /billing/invoices` | Keep |
| 13 | Invoice Detail: INV-1042 | `/billing/invoices/:id` | `POST …/payments`, `…/void` | Keep |
| 14 | Deal Health and Anomaly | `/deal-health` | `/dashboard/deal-health`, `/attention-items`, `/reports/discount-anomalies` | Keep, extend |
| 15 | Admin / Reporting *(Optional)* | `/reports` | 5 reports + `/reports/{name}/export` | **Not optional** — fully supported |
| 16 | Product catalog | `/products`, `/admin/products` | `GET /products`, `/admin/products` | Keep |
| 17 | Product and pricelist | `/admin/products/:id` | `/admin/products`, `/product-variants`, `/price-lists` | Keep |
| 18 | Discount tiers and approval chains | `/admin/policies` | `GET /policies`, `/admin/policies`, `/admin/settings` | Keep — flagship admin screen |

---

## Where the wireframe is already right

Several callouts describe behaviour the backend genuinely implements. These are
not aspirations to design around — they are contracts to render.

| Wireframe says | Backend reality |
|---|---|
| Screen 4: *"Discount is checked against each line's own limit live, as soon as it is entered, not only at submit time."* | `POST /calculate` re-runs the policy engine on every line change; `GET /policy-results` returns per-line results. Correct as drawn |
| Screen 4 columns `Discount / Limit / Status` with `OVER (+8pt)` | `policy_results[].actual_value`, `.threshold_value`, `.overage_points`. The wireframe invented no field |
| Screen 6: *"Worst single line (8pt over) plus overall pattern across the order sets the blended score. One bad line is enough to require approval."* | Exactly the risk model: `WEIGHTED_DISCOUNT_OVERAGE` + `VIOLATION_BREADTH` + `MARGIN_SHORTFALL` + `DISCOUNT_DEPTH`, each capped and individually explained |
| Screen 6 stepper: Submitted → Sales Manager → Finance → Confirmed | `approval_request.steps[]` with `level` and `status`, ordered `SALES_MANAGER → FINANCE → EXECUTIVE` |
| Screen 6 actions: Approve / Return for Revision / Reject | `POST …/approve`, `…/request-revision`, `…/reject` — a three-way match |
| Screen 8: *"'Consolidate Remaining Backorder' prompt appears automatically once East Depot restocks."* | `POST /admin/inventory/adjust` — "a receipt also consolidates backorders" |
| Screen 8 table `Warehouse / Qty / Est. Shipments / Cost` + Accept Suggested Split / Manual Override | Allocation returns `splits[]`, `shipment_count`, `estimated_shipping_cost`; `overrides[]` is a real request field |
| Screen 11: *"If final terms exceed thresholds, the quote automatically re-enters approval (Screen 6)."* | The stale-approval loop, verified live: counter-offer → v2 → approval invalidated → confirm returns 409 `STALE_APPROVAL` |
| Screen 13: *"Partial invoicing stays reconciled with partial delivery, nothing is billed before it ships."* | Billing schedules are per order line and per period |
| Screen 14 cards: Stalled Deals / Discount Anomalies / Delivery Slippage | `AttentionItemType.STALLED_DEAL`, `DISCOUNT_ANOMALY`, `DELIVERY_SLIPPAGE` — three of the eleven types, named identically |
| Screen 14 actions: Escalate / Nudge Rep | `POST /dashboard/attention-items/{id}/escalate` and `/nudge` |
| Screen 18: tier ceilings (Bronze 5 / Silver 10 / Gold 15) and category ceilings (Hardware 15 / Services 10) | Seeded policies. The live run reported *"exceeds the Gold tier ceiling of 15%"* for hardware and *"of 10%"* for services |
| Screen 18 chain: within limit → none · over, medium risk → Sales manager · over, high risk → Sales manager then Finance | `policy.required_action` drives routing. The canonical quote routed `SALES_MANAGER → FINANCE` at risk 32.44 |
| Screen 15 filters: Period / Sales Team / Approval Status / Product | `period` param, `/admin/sales-teams`, `/reports/approval-status`, `/reports/products` |
| Screen 15: Export PDF / Export XLS | `GET /reports/{name}/export?format=pdf\|xlsx\|csv` — verified for all 5 reports |

---

## Where the wireframe and backend disagree

Resolved in the backend's favour. The wireframe does not get to invent state.

| # | Wireframe | Backend | Resolution |
|---|---|---|---|
| 9 | Subscription status chips **Active / Paused / Cancelled** | `BillingScheduleStatus` = `SCHEDULED` `ACTIVE` `INVOICED` `COMPLETED` `CANCELLED`. **There is no `PAUSED`** | Drop "Paused". Render the five real statuses. Pausing would be fake |
| 17 | Recurring interval **Monthly / Yearly / Weekly** | `RecurringInterval` = `MONTHLY` `QUARTERLY` `YEARLY`. No `WEEKLY`; `QUARTERLY` omitted from the wireframe | Offer the three real intervals |
| 3 | Kanban columns: Draft, Pending Approval, Approved, Negotiation, Confirmed | `QuoteVersionStatus` has **8**: adds `SENT`, `REJECTED`, `SUPERSEDED` | Add a `SENT` column — it is the state a quote sits in while awaiting the customer, and hiding it loses the pipeline's waiting stage. `REJECTED`/`SUPERSEDED` are terminal: filter, not columns |
| 2 | "3 flagged by Deal Health" as a static count | `/control-tower` returns severity-ranked items with owner and recommended action | Show the queue, not just the count |
| 15 | Titled "(Optional)" | All 5 reports and all 3 export formats verified working | Build it. Nothing optional about a working capability |
| 17 | "Quantity on hand" on the product form | Stock is per warehouse (`inventory` is keyed by warehouse × product) | Show per-warehouse stock; a single number would misrepresent the model |
| 6 | Final stepper node "Confirmed" | Confirmation is the **customer's** act, not an approval step | Keep it in the visual chain — it is the truthful end of the journey — but style it as a distinct phase, not a fourth approver |

---

## Screens added beyond the wireframe

Only where the backend has a real capability the board omits. Each has an
endpoint; none is speculative.

| Route | Why | Endpoint |
|---|---|---|
| `/quotes/:id/impact/:vid` | **The largest omission.** The board shows the stale-approval loop only as a callout on Screen 11 and a dashed arrow to Screen 6. `/impact` returns a field-level diff, severity-rated material changes, invalidated decisions, and `blocks_confirmation`. §17 asks for the "wow" screen; the data for it exists and the wireframe has nowhere to put it | `GET /quote-versions/{id}/impact` |
| `/quotes/:id/…/simulate` (panel) | What-if scoring without persisting; returns approvals added/removed and a prose verdict | `POST …/simulate` |
| `/deals` | Deals are a first-class object with 5 stages; the board jumps straight to quotations | `GET /deals` |
| `/customers`, `/customers/:id` | Tier and payment terms drive every ceiling on Screen 18 | `GET /customers` |
| `/activity` | Append-only audit with actor and role — verified 24 ordered events for one quote | `/audit/events`, `/audit/quotes/{id}/timeline` |
| `/admin/warehouses` | `priority` and `shipping_cost_per_shipment` are what *produce* Screen 8's suggested split | `/admin/warehouses` |
| `/admin/settings` | Governance tuning: risk weights, finance escalation threshold, SLA hours, anomaly sigma. Changing a weight visibly re-routes approvals — the strongest available proof that Screen 18's chain is not hardcoded | `GET/PATCH /admin/settings` |
| `/admin/users`, `/admin/sales-teams` | User administration; teams enable Screen 15's Sales Team filter | `/users`, `/admin/sales-teams` |

---

## Deliberate upgrades

| Screen | Wireframe | Built instead | Why |
|---|---|---|---|
| 2 Dashboard | Three summary cards + Recent Activity | **Command Center**: severity-ranked action queue, `my_queue` first, prose headline, each item carrying reason / impact / owner / recommended action | `/control-tower` already returns ranked work. Reducing it to "4 quotations waiting" throws away the useful part, and §9 explicitly rules out meaningless KPI cards |
| 4 Quotation Detail | One screen that both reads and edits | **Detail** (read, version history, timeline) + **Builder** (edit) | Editing is legal only in DRAFT (`is_editable`). One screen silently changing capability by status is the kind of ambiguity that produces 409s the user cannot predict |
| 4 Builder layout | Single column | **Split: workspace │ decision intelligence** | §15. The right panel answers what is happening, why, what the impact is, what needs approval — all four already in `policy-results` + `simulate` + `recommendations` |
| 6 Approval Detail | Flat "Why This Quote Was Flagged" table | Keep the table, add the **blended-risk decomposition**: four weighted components, each with its raw value, weight, cap, and the backend's own explanation string | The wireframe's callout describes the model in prose; the API returns it structured. Showing the arithmetic is what makes the score trustworthy |
| 11 Portal | One negotiation screen | Three tabs as the key implies: My Quotation / Messages / Profile, in a **visually distinct shell** — lower density, wider measure, larger type | §14. It must read as a proposal, not a console |
| 14 Deal Health | Three cards + two-row table | Control tower: per-deal score, band, and itemised `signals[]` with point deductions, plus all 11 attention types | The board shows 3 of 11 types. Each backend item already carries what / why / impact / action — §18's four questions, pre-answered |
| 18 Discount tiers | Static config form | Config **plus** live effect: editing a ceiling or a risk weight shows which pending quotes would re-route | Turns the most abstract screen into the clearest demonstration that routing is policy-driven |

---

## The canonical journey as a route walk

Every step below was executed against the live API during Phase 0; these are
observed values, not targets. This becomes the Phase 12 E2E script.

```
1  /login                    POST /auth/login                → is_internal → /
2  /                         GET  /dashboard/control-tower
3  /quotes                   GET  /quotes                    (Kanban + table)
4  /quotes/:id/…/build       POST /deals · /deals/{id}/quotes
                             POST …/lines ×4
                             POST …/calculate                → 132,710.00 · 24.4970%
                             GET  …/policy-results           → risk 32.4440 MEDIUM
                                                             → 4 violations, 3 lines over ceiling
                             POST …/submit                   → SALES_MANAGER → FINANCE
5  /approvals    (manager)   GET  /approvals/inbox
6  /approvals/:id            POST …/approve                  → step 1 APPROVED
6  /approvals/:id (finance)  POST …/approve                  → version APPROVED
4  /quotes/:id               POST …/send                     → SENT
11 /portal/quotes/:id (cust) GET  /portal/quotes/{q}         → redaction verified clean
                             POST …/messages COUNTER_OFFER   → v2, requires_reapproval
++ /quotes/:id/impact/:v2    GET  …/impact                   → 4 material changes
                                                             → 1 approval invalidated
11 /portal/quotes/:id        POST …/confirm                  → 409 STALE_APPROVAL
6  /approvals/:id (m + f)    POST …/approve ×2               → re-approved
11 /portal/quotes/:id        POST …/confirm + Idempotency-Key → order SO-000NN
                             POST …/confirm (same key)       → idempotent_replay: true
8  /orders/:id               POST …/allocate                 → 60 MAIN + 40 EAST, 2 shipments
                             POST …/fulfill
13 /billing/invoices         GET  /billing/orders/{o}/summary → 3 one-time + 1 yearly
                             POST /billing/invoices · …/payments
++ /activity                 GET  /audit/quotes/{q}/timeline → 24 ordered events
14 /deal-health              GET  /dashboard/deal-health/{d} → 100/100 HEALTHY
```

`++` marks a screen the wireframe does not contain.
