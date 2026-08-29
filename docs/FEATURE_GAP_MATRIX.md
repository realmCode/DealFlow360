# FEATURE_GAP_MATRIX

Three questions per capability: does the **backend** do it, does the **frontend**
need to show it, and is there a **gap**. Backend status is from execution against
the live API, not from documentation.

Frontend status is `[ ]` for everything because no frontend exists
(`FRONTEND_CURRENT_STATE.md`).

---

## A. Backend gaps

**None found in application behaviour.** Every capability the documentation
claims was executed against the running server and produced correct results,
including the ones most likely to be faked in a hackathon build: blended risk,
material-change detection, approval staleness, multi-warehouse allocation,
proration, and recommendations.

What *was* broken sat in the verification layer — the machinery that proves the
backend works. Left alone, it would have made every later "the tests pass"
claim worthless.

| # | Defect | Why it mattered | Fix | Verified |
|---|---|---|---|---|
| 1 | **Test suite deadlocked; could not complete.** 16 of 24 test modules ran their async tests on a function-scoped event loop while the SQLAlchemy engine is session-scoped. The first such test raised `RuntimeError: got Future attached to a different loop`, its teardown then failed, leaving a PostgreSQL connection `idle in transaction` holding row locks. The next test blocked on that lock forever. | Nothing could be verified. A run appeared to "still be going" rather than failing, so the suite looked slow instead of broken. `PROGRESS.md` claimed 344 passing; that was not reproducible in this checkout. | `tests/conftest.py`: `item.add_marker(..., append=False)`. `add_marker` appends, and pytest-asyncio's auto-mode marker was already first, so it won `get_closest_marker`. Prepending makes the session-scoped marker the closest one. One line, fixes all 16 modules. | Suite now completes: **434 passed in 65s** |
| 2 | **`pytest.ini` declared an option the pinned library ignores.** `asyncio_default_test_loop_scope` requires pytest-asyncio ≥ 0.26; `requirements.txt` pins 0.25.0. It emitted `PytestConfigWarning: Unknown config option` and did nothing. | This is *why* defect 1 was invisible: the file said the loop scope was pinned, so the 8 modules that also set `pytestmark` looked redundant rather than load-bearing. | Removed the dead option; documented that `tests/conftest.py` pins the test-side scope. | Warning gone |
| 3 | **`test_development_keeps_the_permissive_defaults` failed for anyone who followed the README.** It asserts the class default `cors_origin_list == ["*"]`, but `Settings` reads `.env`, and `.env.example` — which the README says to copy — sets `CORS_ORIGINS=http://localhost:5173,...`. | A red suite on a correctly configured machine. The `.env` is right; the test was not hermetic. Note the value it trips over is exactly the one the frontend needs. | Construct with `_env_file=None` so it tests class defaults. | 11/11 in that module |
| 4 | **`scripts/self_audit.py` cited a test that no longer exists.** Question 17 ("can seed data be run twice safely?") pointed at `test_models.py::test_exactly_thirty_three_tables_are_mapped` — renamed, and about table counts, not seeding. The script exited non-zero. | The self-audit is the "is any of this faked?" gate. It could not run, and question 17 had **no** proof: seed idempotency was genuinely untested. | Wrote `test_seeding_twice_creates_nothing_the_second_time` (asserts the second run creates 0 rows, ids stay stable, and reserved stock is undisturbed) and repointed the citation. | Self-audit **20/20 PASSED** |
| 5 | **Stale counts in `self_audit.py` and `README.md`.** Both said 33 tables / 95 NUMERIC columns; the schema has grown to 38 tables / 110 NUMERIC columns. | Cosmetic, but these numbers are quoted as evidence. | Corrected to the values `verify_db` reports. | `verify_db` PASSED |

Nothing was rewritten. No application code under `app/` was modified.

---

## B. Backend capability → frontend requirement

Legend: **BE** ✅ verified live · **FE** `[ ]` not started · **Flagship** = one of the four screens the directive calls out.

### Identity and access
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Login / signup / refresh | `POST /auth/{login,signup,refresh}` | ✅ | `[ ]` | 60-min access token, 7-day refresh, `token_type: bearer` |
| Session bootstrap | `GET /users/me` | ✅ | `[ ]` | `is_internal` decides which of the two app shells loads |
| Six roles | `SALES MANAGER FINANCE OPS ADMIN CUSTOMER` | ✅ | `[ ]` | Role guards read live from the dependency graph |
| Tenant isolation | all | ✅ | `[ ]` | Cross-tenant returns **404**, never 403 — never render "permission denied" for it |
| User administration | `GET/POST /users` | ✅ | `[ ]` | ADMIN only |

### Commercial core
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Deal pipeline | `GET/POST/PATCH /deals` | ✅ | `[ ]` | 5 stages; `Page` envelope |
| Quote workspace list | `GET /quotes` | ✅ | `[ ]` | 28 fields per row incl. `margin_pct`, `blended_risk_score`, `risk_band`, `is_stale` — a genuinely dense table without extra requests |
| Quote + versions | `POST /deals/{id}/quotes`, `GET /quote-versions/{id}` | ✅ | `[ ]` | 8 version statuses |
| Line editing | `POST/PATCH/DELETE .../lines` | ✅ | `[ ]` | DRAFT only; gate on `is_editable`, expect 409 `IMMUTABLE_VERSION` |
| Order-level discount | `PATCH .../discount` | ✅ | `[ ]` | Compounds with line discounts |
| Authoritative recalculation | `POST .../calculate` | ✅ | `[ ]` | **Flagship.** Returns all totals + risk in one payload |
| What-if simulation | `POST .../simulate` | ✅ | `[ ]` | **Flagship.** `persisted: false`; returns deltas, approvals added/removed, prose verdict |
| Explainable policy results | `GET .../policy-results` | ✅ | `[ ]` | **Flagship.** Per-policy `reason`, `risk_contribution`, `overage_points` |
| Blended risk decomposition | in policy-results | ✅ | `[ ]` | **Flagship.** 4 weighted components, each with its own `explanation` and cap |
| Recommendations | `GET /quotes/{id}/recommendations` | ✅ | `[ ]` | Real: `kind`, `reason`, `impact`, `confidence`, estimated revenue/margin |
| Dismiss recommendation | `POST .../dismiss` | ✅ | `[ ]` | Only place optimistic UI is safe |
| Mark lost | `POST /quotes/{id}/lose` | ✅ | `[ ]` | Closes the deal |

### Approvals and staleness
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Auto-routing on submit | `POST .../submit` | ✅ | `[ ]` | Routing derived from policy, never manual |
| Ordered steps | in approval request | ✅ | `[ ]` | **Flagship.** `SALES_MANAGER → FINANCE → EXECUTIVE` |
| Approver inbox | `GET /approvals/inbox` | ✅ | `[ ]` | MANAGER/FINANCE/ADMIN; SALES gets 403 |
| Decision detail | `GET /approvals/{id}` | ✅ | `[ ]` | **Flagship.** Includes `financials`, `steps`, `decisions`, `policy_summary` |
| Approve / reject / request revision | `POST .../{action}` | ✅ | `[ ]` | Body requires `reason` |
| Self-approval ban | — | ✅ | `[ ]` | 403 `SELF_APPROVAL_FORBIDDEN` |
| **Material-change detection** | `GET .../impact` | ✅ | `[ ]` | **Flagship.** Field-level old→new with severity and prose reason |
| **Approval staleness** | same | ✅ | `[ ]` | **Flagship.** `stale_decisions[]`, `blocks_confirmation: true` |
| **Confirmation blocked** | `POST /portal/.../confirm` | ✅ | `[ ]` | **Flagship.** 409 `STALE_APPROVAL` with a customer-safe message |
| Re-approval | same approve route | ✅ | `[ ]` | **Flagship.** New request supersedes the stale one |

### Customer portal
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Redacted quote list/detail | `GET /portal/quotes[/{id}]` | ✅ | `[ ]` | Verified: no cost, margin, or risk field appears |
| Negotiation thread | `GET/POST .../messages` | ✅ | `[ ]` | 6 message types |
| Counter-offer → new version | `POST .../messages` type `COUNTER_OFFER` | ✅ | `[ ]` | Returns `new_version_id`, `requires_reapproval` |
| Seller side of thread | `GET/POST /quotes/{id}/negotiation[/reply]` | ✅ | `[ ]` | Same conversation, unredacted |
| Confirm (idempotent) | `POST .../confirm` | ✅ | `[ ]` | `Idempotency-Key`; replay returns `idempotent_replay: true` |

### Orders, inventory, fulfilment
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Orders list/detail | `GET /orders[/{id}]` | ✅ | `[ ]` | 7 statuses |
| Multi-warehouse allocation | `POST /orders/{id}/allocate` | ✅ | `[ ]` | Per line: `splits[]` + prose `explanation`; `shipment_count`, `estimated_shipping_cost` |
| Backorders | same | ✅ | `[ ]` | Verified live: exhausted stock produced a `BACKORDER` split |
| Manual override | `overrides[]`, `allow_partial` | ✅ | `[ ]` | |
| Fulfil | `POST /orders/{id}/fulfill` | ✅ | `[ ]` | One shipment per warehouse |
| Deliver | `POST .../fulfillments/{id}/deliver` | ✅ | `[ ]` | |
| Cancel + release stock | `POST /orders/{id}/cancel` | ✅ | `[ ]` | |
| Promised date / slippage | `PATCH /orders/{id}/promise` | ✅ | `[ ]` | SALES/MANAGER/ADMIN — **not** OPS |
| Stock levels | `GET /inventory` | ✅ | `[ ]` | `available = on_hand − reserved` |

### Billing
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Schedules (one-time + recurring) | `GET /billing/schedules` | ✅ | `[ ]` | Coexist on one order |
| Order billing summary | `GET /billing/orders/{id}/summary` | ✅ | `[ ]` | Verified 3 one-time + 1 yearly |
| Invoice issue / pay / void | `POST /billing/invoices[...]` | ✅ | `[ ]` | FINANCE/ADMIN; `is_overdue` is computed, not a status |
| Subscription change | `POST /billing/subscriptions/{id}/change` | ✅ | `[ ]` | Quantity/interval with proration |
| Subscription cancel | `POST .../cancel` | ✅ | `[ ]` | Verified: returns periods kept/regenerated + prose explanation |
| Proration preview | `GET /billing/proration-preview` | ✅ | `[ ]` | Requires `full_period_amount`, `billed_from` |
| Credit notes | `GET/POST /billing/credit-notes[...]` | ✅ | `[ ]` | Refund and void |

### Intelligence
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| Control Tower | `GET /dashboard/control-tower` | ✅ | `[ ]` | **Flagship.** Severity groups, `my_queue`, prose `headline` |
| Attention items | `GET /dashboard/attention-items` | ✅ | `[ ]` | **Flagship.** 11 types; each carries `reason`, `impact`, `owner_role`, `recommended_action` — the what/why/impact/action the directive asks for is already in the payload |
| Acknowledge / resolve / nudge / escalate | `POST .../{action}` | ✅ | `[ ]` | |
| Deal health | `GET /dashboard/deal-health[/{id}]` | ✅ | `[ ]` | **Flagship.** Score + band + itemised `signals[]` with point deductions |
| Discount anomalies | `GET /reports/discount-anomalies` | ✅ | `[ ]` | Per-rep sigma, not a global threshold |
| Audit timeline | `GET /audit/events`, `/audit/quotes/{id}/timeline` | ✅ | `[ ]` | Verified 24 ordered events with actor + role |

### Reporting and administration
| Capability | Endpoints | BE | FE | Notes |
|---|---|:--:|:--:|---|
| 5 reports | `/reports/{pipeline,sales-performance,discounts,products,approval-status}` | ✅ | `[ ]` | Period filters |
| Export | `GET /reports/{name}/export` | ✅ | `[ ]` | All 5 × csv/xlsx/pdf verified; binary blob, honour `Content-Disposition` |
| Products / variants / price lists | `/admin/...` | ✅ | `[ ]` | Variants and price lists currently seed empty — build the CRUD, expect empty states |
| Warehouses | `/admin/warehouses` | ✅ | `[ ]` | `priority` and `shipping_cost_per_shipment` drive the split |
| Inventory adjustment | `POST /admin/inventory[/adjust]` | ✅ | `[ ]` | Receipt consolidates backorders |
| Policies | `/admin/policies`, `GET /policies` | ✅ | `[ ]` | 4 policy types |
| Governance settings | `GET/PATCH /admin/settings` | ✅ | `[ ]` | Risk weights, SLA hours, anomaly sigma — tuning these visibly changes routing |
| Sales teams | `/admin/sales-teams` | ✅ | `[ ]` | Enables the team filter on reports |

---

## C. Frontend-only gaps (no backend counterpart — must not be invented)

| Want | Reality | Decision |
|---|---|---|
| Real-time push | No WebSocket or SSE | Refetch after mutation; refetch on focus; 30–60 s poll **only** for Control Tower and approval inbox, only while the tab is visible |
| Logout endpoint | None | Clear client token state |
| Notifications / email | Not implemented | Do not build a bell icon |
| File upload / attachments | Not implemented | Omit |
| Full-text search across entities | Only per-list `search`/filter params | Scope search to each list |
| Saved views, bulk actions | Not implemented | Omit |
| Payment gateway | `POST .../payments` **records** a payment; it does not process one | Label it "Record payment" |
| Password reset | Not implemented | Omit |

Anything in this table that appears in the UI would be fake. It will not be built.

### Drawn in the wireframe but absent from the backend

Found by reading `image.png` against the enums. Full reconciliation in
`REFERENCE_TO_FRONTEND_MAP.md`.

| Wireframe element | Backend | Decision |
|---|---|---|
| Subscription status **"Paused"** (Screen 9) | `BillingScheduleStatus` has `SCHEDULED ACTIVE INVOICED COMPLETED CANCELLED` — no `PAUSED` | Not built. A pause control that cannot pause anything is the definition of fake |
| Recurring interval **"Weekly"** (Screen 17) | `RecurringInterval` = `MONTHLY QUARTERLY YEARLY` | Offer the three real intervals; `QUARTERLY` is missing from the wireframe and will be added |
| **"Quantity on hand"** as a single product field (Screen 17) | Stock is per warehouse — `inventory` is keyed by warehouse × product | Show per-warehouse stock. One number would misstate the model |
