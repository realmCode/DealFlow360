# JUDGE WOW STRATEGY

Every differentiator here is framed as
**PROBLEM → FEATURE → TECHNICAL IMPLEMENTATION → USER VALUE → JUDGE IMPACT**.

Nothing in this document is a buzzword play. Each item is either already built
and under-communicated, or a small addition to something already built. Anything
that would need new infrastructure to justify itself was rejected — see
[`BACKEND_GAP_ANALYSIS.md`](./BACKEND_GAP_ANALYSIS.md) REJECT.

---

## The thesis

The PDF says most sales tools handle "create a quote, confirm an order, invoice
it" and that real teams operate in "messier conditions." Read the mess it lists:

- A discount is approved, then the customer changes the terms.
- Stock is promised from a warehouse that then runs dry.
- A subscription is quoted, then the quantity changes mid-cycle.
- A deal is fine, then goes quiet.

**Every one of those is the same failure: a decision made at time T is still
being trusted at time T+1 after its premises moved.**

That is the insight to lead with. Most teams will build the seven bullet points
in PDF §1 as seven screens. A team that recognises they are four instances of
one problem — and builds a mechanism that detects premise drift, invalidates the
affected decision, re-routes it, and blocks downstream execution until a human
re-decides — is answering a deeper question than was literally asked.

The demo should make a judge think: *"they didn't just implement the spec, they
worked out what the spec was about."*

---

## Tier 1 — already built, must be shown clearly

These are the strongest assets and the biggest communication risk. They exist
and work; if the demo does not surface them, the judge scores a generic CRUD app.

---

### W1 · Approval staleness — the decision that expires when reality moves

| | |
|---|---|
| **PROBLEM** | A quote is approved at 18% discount. The customer negotiates to 25%. In every naive system the approval silently continues to authorise terms nobody actually signed off. The company ships an order on a decision that was never made. |
| **FEATURE** | A material change to an approved version invalidates the prior approval, marks it `STALE` (retained, never deleted), re-opens the approval chain, raises a CRITICAL alert owned by Finance, and **blocks order confirmation with 409 `STALE_APPROVAL`** until a human re-decides. |
| **TECHNICAL IMPLEMENTATION** | `DecisionFabric.detect_changes` field-diffs two versions with **fail-closed materiality epsilons** (`discount_pct` > 0.01pp, `margin_pct` > 0.10pp, `total_revenue` > 0.10% relative, any quantity change). Lines are matched by **provenance** (`quote_lines.source_line_id`), not position, so an add-plus-remove is not mis-reported as an innocuous product swap. `ApprovalService.invalidate_prior_approvals` transitions the request to `STALE` with `stale_at`/`stale_reason` and links the replacement via `superseded_by_request_id`. `assert_confirmable` is the gate. All of it in **one transaction**, so there is no window where a superseded version exists without its governance evaluation. |
| **USER VALUE** | Finance stops being the last to know. The rep cannot accidentally ship unapproved terms. The customer gets a truthful "under review" instead of silence. |
| **JUDGE IMPACT** | **Highest in the project.** This is the one feature that is genuinely hard to fake, because faking it requires the version history, the diff engine, the approval state machine and the confirmation gate to all be real. Ask a competing team to counter-offer twice in a row and watch what happens to their approval record. |

**Demo beat.** Counter-offer at 25% → show v1 still reading 132,710.00 and
`SUPERSEDED` → show v2 at 124,310.00 with margin dropped 24.4970% → 19.3951% →
show the Finance approval flipped to `STALE` with its reason → click Confirm as
the customer → **409** → show the customer sees only *"Your requested changes are
being reviewed by our team"* with no margin or policy leaked.

---

### W2 · Explainable blended risk — a score that shows its arithmetic

| | |
|---|---|
| **PROBLEM** | PDF §10 asks the score to decide *who must review*. A bare number cannot carry that authority — an approver told "risk 32" has no basis to agree or disagree, and a rep told "needs Finance" cannot learn what to do differently. |
| **FEATURE** | Four additive, individually-capped components, each returned with its raw value, weight, points, cap and a prose explanation, plus the formula string and the tier sensitivity applied. |
| **TECHNICAL IMPLEMENTATION** | `C1` weighted discount overage = Σ(overage × revenue_share) × 3.0, cap 45 — **revenue-weighted**, so 8 points over on a $410 service line does not outrank 3 points over on $98,400 of hardware. `C2` breadth = violating_lines × 5.0, cap 15 — this is the term that satisfies the PDF's "many lines each a little over" concern. `C3` margin shortfall = max(0, floor − actual) × 5.0, cap 40. `C4` depth = effective_discount_pct × 0.4, cap 15 — reacts to total giveaway even when every line is compliant. Then `min(100, sum × tier_sensitivity)`. Caps sum to 115, so the clamp is real rather than decorative. Weights are configurable, not magic numbers. |
| **USER VALUE** | An approver sees exactly which lines drove the escalation and by how much. A rep learns the shape of the policy instead of guessing. |
| **JUDGE IMPACT** | Very high. PDF §10 is the longest conceptual section in the document — the authors clearly consider it the intellectual core. A team that returns the decomposition with prose is visibly engaging with that section rather than pattern-matching "risk score". |

**Demo beat.** Show the canonical quote scoring 32.4443 MEDIUM, then read the
components aloud: 7.5072 from weighted overage, 15.0000 from three violating
lines, 0.0000 from margin because 24.4970% clears the 10% floor, 6.9876 from
17.4689% total discount depth, × 1.10 for GOLD tier. Then explain that the
signing-authority policy contributes **zero** to the score but still routes
Finance — because *who signs* and *how risky* are different questions, and mixing
currency into a percentage-point score would make the number meaningless.

---

### W3 · Structural redaction — the portal cannot leak because the fields do not exist

| | |
|---|---|
| **PROBLEM** | PDF §7 makes it a hard constraint: the customer view must be "a real, separate, restricted view, not just another internal screen with a different label." The usual implementation filters fields at the call site, which fails the first time someone adds an endpoint and forgets. |
| **FEATURE** | Portal response models **do not declare** cost, margin, or risk fields at all. Redaction is a type-level property, not a runtime behaviour. |
| **TECHNICAL IMPLEMENTATION** | `QuotePublicRead`, `QuoteVersionPublicRead`, `QuoteLinePublicRead` and `OrderPublicRead` omit `unit_cost`, `line_cost`, `line_margin`, `line_margin_pct`, `total_cost`, `margin`, `margin_pct`, `blended_risk_score`, `risk_band`, `requires_approval` and `stale_reason` entirely. Authorization is **bidirectional** — `require_customer_user` blocks employees from portal routes, so the redacted view can never be used as a substitute for the internal one. `DRAFT` versions are filtered by `CUSTOMER_HIDDEN_VERSION_STATUSES`. The blocked reason is a deliberately safe paraphrase. The end-to-end test asserts the serialised payload contains none of the forbidden substrings **nor the literal internal values** (100200, 32510, 24.4970, 800.0000). |
| **USER VALUE** | The seller can hand a customer a live negotiable document without a data-leak review. |
| **JUDGE IMPACT** | High, and it converts a compliance checkbox into an engineering statement. The line worth saying: *"a developer cannot forget to redact a field that doesn't exist in the schema."* |

---

### W4 · Emergent warehouse split — nothing about 60/40 is written down

| | |
|---|---|
| **PROBLEM** | The demo-friendly answer is to hardcode the split the sample data produces. PDF §7 explicitly forbids that: rules must be "implemented in application logic, not hardcoded or faked for the demo." |
| **FEATURE** | A generic cost-minimising allocator. 60/40 is an *output* of the seed data, not an input to the algorithm. |
| **TECHNICAL IMPLEMENTATION** | Rule 1: if any single warehouse can cover the line, use it — one shipment beats two — tie-broken by lowest `priority`, then lowest shipping cost, then largest stock, then code. Rule 2: otherwise take largest-available-first to minimise shipment count. Rule 3: the remainder becomes a `BACKORDERED` allocation with **no warehouse** (enforced by a CHECK constraint) carrying the earliest expected restock date. `test_split_changes_when_stock_changes` rebalances the seed to 30/70 and asserts the split follows. |
| **USER VALUE** | Ops gets a defensible recommendation with an `explanation` string and shipment cost, and can still override — with the override validated against real availability. |
| **JUDGE IMPACT** | High **if demonstrated by changing the data live.** Adjust stock, re-allocate, show a different split. That single action proves the algorithm is real and is the fastest way to distinguish this from a scripted demo. |

---

### W5 · Provable concurrency safety

| | |
|---|---|
| **PROBLEM** | Two orders race for the last unit of stock; two approvers click at once; a customer double-clicks Confirm. Naive systems oversell, double-approve, or create two orders. |
| **FEATURE** | Every one of those is impossible, at two independent layers each. |
| **TECHNICAL IMPLEMENTATION** | Allocation takes `SELECT ... FOR UPDATE` over all stock rows for the product **before deciding anything**, locking in `inventory.id` order with lines processed in `product_id` order — identical lock ordering in every transaction, eliminating the deadlock window. Backstop: `CHECK (quantity_reserved <= quantity_on_hand)`. Confirmation is protected by a SHA-256 body fingerprint under `SELECT FOR UPDATE` **and** `UNIQUE (sales_orders.quote_version_id)` above it, so even with no `Idempotency-Key` a duplicate order cannot exist. A reused key with a *different* body returns 409 rather than silently replaying the wrong response. Approvals serialise on `current_step_sequence`; a partial unique index guarantees at most one `PENDING` approval per version. |
| **USER VALUE** | Nobody has to think about it. That is the point. |
| **JUDGE IMPACT** | High with a technical judge, invisible otherwise. Have `pytest -m concurrency` ready to run. "We have tests that open two transactions against the same stock row" is a short sentence with a lot of weight. |

---

### W6 · Complete, ordered, actor-attributed audit trail

| | |
|---|---|
| **PROBLEM** | PDF A3 requires every approval, rejection and edit logged with user, timestamp and reason. The real question behind it is accountability: *who authorised this, and what were they looking at?* |
| **FEATURE** | 25 event types, one call to retrieve a quote's entire history, and every approval decision stores a snapshot of the financials the approver actually saw. |
| **TECHNICAL IMPLEMENTATION** | An in-process event bus whose handlers run on the **caller's session**, so an audit row and the state change it describes commit or roll back together — a broker could not offer that. A global `@subscribe_all` subscriber means no service can forget to log. `audit_events` has **no `updated_at` column**, so there is structurally nothing to rewrite history with. A monotonic `BIGINT IDENTITY` `sequence` gives stable total ordering because a single transaction emits several events in the same microsecond. Money in payloads is stored as **strings** — a float round-trip through JSONB would corrupt the record of a decision, and a test walks every payload to prove none exists. |
| **USER VALUE** | "Why did we sell at this price?" is one request: `GET /audit/quotes/{id}/timeline`, 22 ordered events for the canonical flow. |
| **JUDGE IMPACT** | Medium-high. The differentiating detail is `decision_snapshot` — most audit trails record *that* someone approved; this one records *what they were looking at when they did*. |

---

## Tier 2 — small additions, high demo yield

Ordered by demo value per line of code.

---

### W7 · What-if simulation — turn the risk score into a planning tool

| | |
|---|---|
| **PROBLEM** | The rep discovers the approval consequence *after* submitting. They cannot ask "what if I gave 20% instead of 25%?" without committing a revision and dragging Finance through it. |
| **FEATURE** | `POST /quote-versions/{id}/simulate` — evaluate hypothetical line changes and return the would-be blended risk, band, required approvers and margin, **persisting nothing**. |
| **TECHNICAL IMPLEMENTATION** | `PolicyEngine.evaluate` is **already a pure function** of `(version, lines, profile, policies)`. `CommercialEngine.calculate_line` is likewise pure. So this is: clone the loaded lines in memory, apply the overrides, call the two existing pure functions, return the result. No new table, no migration, no writes. Genuinely mostly plumbing. |
| **USER VALUE** | The rep self-serves the governance question and lands inside policy on the first submit. Fewer escalations, faster cycle. |
| **JUDGE IMPACT** | **Very high per unit of effort.** It demos as a slider: drag the discount, watch "Requires: Sales Manager" become "Requires: Sales Manager + Finance" live. It also proves the engine is a real pure function rather than a code path that only runs on save — which retroactively strengthens W2's credibility. |

---

### W8 · Discount anomaly vs the rep's own history

| | |
|---|---|
| **PROBLEM** | PDF B9 asks for "a discount well above a **rep's historical average**." A ceiling check cannot see this: a rep who normally quotes 4% suddenly quoting 14% is an anomaly even though 14% clears a 15% ceiling. The current system is **structurally blind** to behavioural drift. |
| **FEATURE** | A rolling per-rep baseline. Flag a submission that deviates materially from that rep's own pattern, with the arithmetic stated. |
| **TECHNICAL IMPLEMENTATION** | Compute mean and standard deviation of `effective_discount_pct` over that rep's recent submitted versions, with a minimum sample size before the baseline is trusted. Flag when `value > mean + k × stdev`, `k` configurable per organization. New `AttentionItemType.DISCOUNT_ANOMALY` owned by `MANAGER`, severity scaled by deviation magnitude. Evaluated inside `DecisionFabric.process_version`, so it reuses the existing decision-point plumbing and the anti-spam partial unique index. |
| **USER VALUE** | Catches erosion that policy cannot: a rep drifting upward within limits, or one account being systematically favoured. |
| **JUDGE IMPACT** | High. This is the one place the PDF asks for a **deeper idea than a threshold** and the current implementation does not have it. Closing it — and articulating why it is different from a ceiling check — directly demonstrates having read past the surface. The alert must state its reasoning: *"18% is 3.2 standard deviations above Sam Rivera's 12-quote average of 6.4%"*. A bare flag would undercut the whole explainability story. |

---

### W9 · Co-purchase-derived recommendations

| | |
|---|---|
| **PROBLEM** | PDF A6.1 asks for pairings from "historical co-purchase data". The current engine uses three sensible heuristics instead, which is defensible but is not what was asked. |
| **FEATURE** | Mine real attach rates from `sales_order_lines`: "68% of orders containing this laptop also contain the installation service." |
| **TECHNICAL IMPLEMENTATION** | A self-join aggregate over historical order lines producing product-pair support and confidence. Blend with the existing margin ranking. Keep it deterministic and explainable — a lift/confidence figure, not a model. Falls back to the current heuristics when history is thin, which is honest and also necessary for a fresh demo database. |
| **USER VALUE** | Suggestions carry evidence, so the rep trusts them enough to use them. |
| **JUDGE IMPACT** | Medium-high. It makes QT4 substantive rather than merely passing, and "we computed attach rates from order history, with a documented cold-start fallback" is a far better answer than "we hardcoded pairings." |

---

### W10 · Deal replay — reconstruct any past state

| | |
|---|---|
| **PROBLEM** | Six months later: "why was this approved?" The terms have changed three times since. |
| **FEATURE** | Replay a quote's full state at any point in its history. |
| **TECHNICAL IMPLEMENTATION** | **The data already exists.** `commercial_snapshots` holds full line-level detail as JSONB per calculation with one `is_current` per version; `approval_decisions.decision_snapshot` holds the financials at each decision; `decision_impacts` holds every diff — material or not, so the system can also state *"we looked at this and it did not matter"*; `audit_events` gives monotonic ordering. This is an assembly endpoint over existing rows, not new capture. |
| **USER VALUE** | Dispute resolution and audit defence become a query instead of an archaeology project. |
| **JUDGE IMPACT** | Medium-high, and it closes the loop on W1 rhetorically: the system prevents stale decisions **and** can prove what every past decision was based on. |

---

## Tier 3 — cheap credibility wins

| ID | Item | Effort | Why it pays |
|---|---|---|---|
| W11 | **Seed a `PAYMENT_TERMS_LIMIT` policy** | One seed row | The evaluator is **fully implemented** and never fires because nothing seeds it. One row demonstrates a fourth policy type and makes the governance engine look broader at zero code cost. |
| W12 | **Reorder-point alerts** | Small | `inventory.reorder_point` is stored and nothing acts on it. Completes PDF A4.3 and adds a proactive Ops signal. |
| W13 | **Approval SLA tracking** | Small | `waiting_since` is already in the inbox payload. Add a threshold and surface breaches — pairs naturally with the nudge/escalate actions PDF B9 requires. |
| W14 | **Nudge and escalate on alerts** | Small | Required by B9 anyway. Turns the Control Tower from a list into a workflow, which is the difference between a dashboard and an action queue. |

---

## Demo choreography — five minutes, two flows

PDF §8 requires a five-minute demo covering at least two full flows. Budget:

| Time | Beat | What the judge should conclude |
|---|---|---|
| 0:00–0:20 | **Frame the thesis.** "Every mess in this problem statement is one failure: a decision outliving its premises. Here is the mechanism that fixes it." | They understood the problem, not just the requirements |
| 0:20–1:10 | **Flow A, build.** Quote with mixed categories. Show per-line ceilings resolving differently — 18% passes on hardware, breaches on services. Accept an upsell, margin updates instantly. Show the risk decomposition with its arithmetic. Submit → routes to Manager then Finance **automatically**. | The governance engine is real and explainable (W2, KO1, KO2) |
| 1:10–1:50 | **Flow A, approve.** Finance tries to jump the queue → **403**. Manager approves, Finance approves, both recorded with reason and the numbers they saw. Send. | Ordered chains, self-approval prevention, audit (W6) |
| 1:50–3:00 | **Flow A, the wow moment.** Customer portal — point out no cost, no margin, no risk **in the schema**. Counter at 25%. Show v1 untouched and `SUPERSEDED`. Show v2's margin collapse. Show the Finance approval flip to `STALE`. Click Confirm → **409**. Show the customer's safe message. Re-approve. Confirm succeeds. | **This is the moment.** (W1, W3, KO6, B8.7) |
| 3:00–3:50 | **Flow A, execute.** Allocation splits 60/40 across two warehouses with its explanation and shipping cost. **Then change the stock and re-allocate to show a different split.** Billing shows 3 one-time schedules plus 1 yearly recurring on one order. Record a payment, invoice flips to PAID. | Nothing is hardcoded (W4, KO3, KO4, QT5, QT6, QT8) |
| 3:50–4:20 | **Flow B, the clean path.** A compliant quote auto-approves on submit and goes straight to fulfillment — and still writes an approval record, so a later change has something to invalidate. | The system is not just a gauntlet; it understands why the auto-approval still needs a record (J4) |
| 4:20–4:50 | **Control Tower + what-if.** Deal health with every deduction named. Discount anomaly against the rep's own average. Drag the what-if slider and watch the required approvers change. | Managers see decay early; reps self-serve governance (W7, W8, KO5) |
| 4:50–5:00 | **Close on the audit timeline.** 22 ordered, actor-attributed events for the deal just built, each carrying the numbers behind the decision. | Complete accountability |

**Two rehearsal rules.** Run the flow against a **freshly seeded** database so
nothing depends on leftover state. And have `pytest -m concurrency` plus
`python -m scripts.verify_db` in a second terminal — if a judge asks "how do you
know inventory can't oversell?", running the test beats describing it.

---

## Anticipated judge questions

Rehearse these. Each has a real answer in the code.

| Question | Answer |
|---|---|
| "Is the 60/40 split hardcoded?" | No. Change the stock and re-run — `test_split_changes_when_stock_changes` rebalances to 30/70 and asserts the algorithm follows. |
| "Why did the score come out 32?" | Read the four components with their arithmetic. Each is returned with raw value, weight, points, cap and prose. |
| "What stops a rep approving their own quote?" | Authorship, not role. `SELF_APPROVAL_FORBIDDEN` fires if the actor is the requester, the version creator, or the quote creator — it catches `ADMIN` too. |
| "What if the customer double-clicks Confirm?" | Two layers: idempotency key with a body fingerprint, and `UNIQUE (sales_orders.quote_version_id)`. Exactly one order, verified by test. |
| "Can a customer see margin?" | The field does not exist in the portal schema. The test asserts the serialised payload contains neither the field names nor the internal values. |
| "What happens if two orders want the last unit?" | `SELECT FOR UPDATE` in deterministic lock order, plus a CHECK constraint as backstop. Tested with concurrent transactions. |
| "Is money floating point?" | Zero float columns. `scripts/verify_db.py` asserts it across all 95 NUMERIC money columns, and money crosses the wire as a JSON **string** so no JS client can lose cents. |
| "Why no Kafka / Redis / microservices?" | The event bus runs handlers in the caller's transaction so audit and state cannot drift. A broker would break that guarantee to solve a problem this system does not have. Documented as a deliberate rejection. |
| "What would you build next?" | Refresh-token revocation, variant-level inventory, wiring price lists into pricing, a background scheduler for outbound nudges, and a transactional outbox for external integration. All documented with rationale. |
| "What is not finished?" | Answer honestly and specifically — reporting export, subscription cancellation, and the fact that product variants and price lists are currently inert. A precise self-assessment reads as competence; a judge who finds an undisclosed gap after being told everything works discounts the whole demo. |

---

## What was deliberately rejected, and why

Being able to explain a *rejection* is itself a differentiator — it shows
judgement rather than accumulation.

| Rejected | Reason |
|---|---|
| ML discount-prediction model | PDF §7 stresses defensible business logic. A judge asking "why did it score 32?" must get arithmetic, not a weight matrix. |
| Message broker | Would break the audit-and-state-in-one-transaction guarantee that the current design provides. |
| Multi-currency FX | PDF §7 calls it a bonus. Large correctness surface, near-zero credit. |
| WebSockets | "Real time" here means recomputed-on-read. Refetch-on-action satisfies every requirement at a fraction of the complexity. |
| Blockchain audit trail | Append-only storage with no `updated_at` and a monotonic sequence is proportionate to the actual threat model. |
| Customer-facing PDF quote | The PDF positions the portal as the explicit replacement for "a static PDF". Building one would contradict the product thesis. |
