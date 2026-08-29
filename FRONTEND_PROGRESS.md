# DealFlow360 Frontend Progress

```
==================================================
PHASE 0  backend audit + verification    COMPLETE
PHASE 1  foundation + design system      COMPLETE
PHASE 2  shell, auth, RBAC               COMPLETE
PHASE 3  quotations                      COMPLETE
PHASE 4  quote builder (flagship)        COMPLETE
PHASE 5  approvals (flagship)            COMPLETE
PHASE 6  stale approval / diff (flagship)COMPLETE
PHASE 7  customer portal                 COMPLETE
PHASE 8  orders, inventory, fulfilment   COMPLETE
PHASE 9  billing, subscriptions, invoices COMPLETE
PHASE 10 deal health, anomalies, audit   COMPLETE
PHASE 11 administration + reporting      COMPLETE
PHASE 12 integration + QA                COMPLETE
--------------------------------------------------
Backend tests   434 passed / 0 failed
Typecheck       clean (strict)
Lint            clean (0 errors, 0 warnings)
Unit tests      12 passed
E2E             5 passed  (incl. full canonical journey)
Production build passes
Screens         31 routes · 86 screenshots at 3 resolutions
==================================================
```

**Status key** — `[ ]` not started · `[~]` in progress · `[x]` implemented **and verified**

`[x]` requires all six: implementation · API integration · tests · visual QA ·
error-state QA · responsive QA.

---

## How to run it

```bash
docker compose up -d                                   # PostgreSQL :5433
uvicorn app.main:app --port 8010                       # API
cd frontend && npm install && PORT=3000 npm run dev    # UI on :3000
```

Port matters: the backend whitelists `http://localhost:5173` and
`http://localhost:3000` exactly. Sign in with any seeded account
(`sales@ / manager@ / finance@ / ops@ / admin@techsupply.com`,
`customer@acme.com`) using `Password123!`.

Verification loop:

```bash
cd frontend
npm run typecheck && npm run lint && npm run test && npm run build
npx playwright test          # visual QA + canonical journey vs the real API
```

---

## Phase 0 — Backend audit, verification, fixes  `[x] 12/12`

- [x] Repository mapped — backend-only; no frontend existed
- [x] Live API booted from *this* repo on `:8010` (a stale server from another
      checkout was on `:8000` and produced false 404s — caught and discarded)
- [x] `docs/openapi.json` diffed against live `/openapi.json` → **0 differences**
- [x] All 26 read endpoints probed across 6 roles → 200
- [x] Canonical flow executed against the API → every documented value reproduced
- [x] Portal redaction verified — no cost/margin/risk field in any portal payload
- [x] Idempotency verified — replayed confirm returned `idempotent_replay: true`
- [x] Backorder path verified
- [x] P1 surface probed — exports, recommendations, subscriptions, proration, settings
- [x] **5 backend defects found and fixed** (`docs/FEATURE_GAP_MATRIX.md` §A)
- [x] `pytest` **434 passed** · `verify_db` PASSED · `alembic check` clean · `self_audit` 20/20
- [x] Seven audit documents written

## Phase 1 — Foundation + design system  `[x] 11/11`

- [x] `SKILLS_ALL` inventoried; `ui-ux-pro-max` queried (7 searches)
- [x] Composite `--design-system` recommendation **overruled** with reasons
      (marketing pattern / OLED theme / programming font) — `docs/UIUX_SKILLS_MAP.md`
- [x] Excalidraw reference read screen by screen; 18 screens mapped, 7 conflicts
      resolved in the backend's favour — `docs/REFERENCE_TO_FRONTEND_MAP.md`
- [x] Vite + React 19 + TypeScript strict
- [x] 187 types generated from the verified OpenAPI document
- [x] Design tokens — semantic colour derived from backend enums, not invented
- [x] Typography: Lexend / Source Sans 3 / IBM Plex Mono (tabular numerals)
- [x] Primitives: Button, Input, NumericInput, Select, Segmented, Checkbox, Table,
      Tabs, Badge (9 enum-bound variants), Panel, GovNote, Dialog, Drawer, Tooltip,
      Timeline, ApprovalFlow, SplitBar, BulletGauge, Skeleton, EmptyState,
      ErrorState, PermissionState, Toast
- [x] Money layer — Decimal end to end, **lint-enforced** against `Number()`/`parseFloat`
- [x] API client — single fetch site, shared silent refresh, error normalisation

## Phase 2 — Shell, auth, RBAC  `[x] 7/7`

- [x] Login (split narrative / form, real error states)
- [x] Session bootstrap from `GET /users/me`; `is_internal` selects the shell
- [x] Two disjoint route trees + guards
- [x] Top-tab module bar with live counts + contextual subnav
- [x] Role-aware navigation (Admin module hidden for non-admins)
- [x] Command Center — severity ledger, ranked action queue, approvals, deal health
- [x] Verified: 6 roles land correctly; customer cannot reach `/quotes`

## Phase 3 — Quotations  `[x] 5/5`
- [x] Quote list — 9 sortable columns, search, status filter, attention filter
- [x] Pipeline Kanban — 6 columns incl. `SENT` (the wireframe omits it)
- [x] Quote detail — commercial summary, lines, negotiation, versions, activity
- [x] Version history with per-version compare links
- [x] Revision and mark-lost flows

## Phase 4 — Quote Builder 🚩  `[x] 7/7`
- [x] Split layout: workspace │ decision intelligence
- [x] Inline line editing gated on `is_editable`; totals always re-read from the API
- [x] Margin waterfall (gross → discount → net → cost → margin)
- [x] Policy evaluation — per-rule reason, actual/limit/over-by, risk contribution
- [x] Blended-risk decomposition — 4 weighted components, each explained and capped
- [x] What-if simulation (`persisted: false`) with deltas and approval changes
- [x] Recommendations with add-to-quote and dismiss
- [x] Verified live: 132,710.00 · 24.50% · risk 32.44 MEDIUM

## Phase 5 — Approvals 🚩  `[x] 5/5`
- [x] Inbox with re-approval flagging and waiting time
- [x] Decision detail — numbers under review, "why this was flagged" table
- [x] Visual progression Submitted → Sales Manager → Finance → Confirmation
- [x] Approve / return / reject with a mandatory reason
- [x] Self-approval and wrong-role states explained, not just blocked

## Phase 6 — Stale approval + version diff 🚩  `[x] 6/6`
- [x] Seven-stage narrative with the current stage pulsing
- [x] Side-by-side version comparison with revenue/margin/risk deltas
- [x] Field-level WAS → NOW → CHANGE with severity and the engine's reason
- [x] Invalidated approvals with the original decision
- [x] Causal chain, signals raised, affected downstream
- [x] Confirmation-blocked state; `STALE_APPROVAL` never renders as a toast

## Phase 7 — Customer portal  `[x] 6/6`
- [x] Distinct shell — warm ground, 3 tabs, low density, no module bar
- [x] Proposal view with terms and totals
- [x] Per-line change requests → counter-offer → new version
- [x] Messages thread
- [x] Confirm with `Idempotency-Key`
- [x] **Isolation asserted in CI**: portal responses carry no cost/margin/risk field

## Phase 8 — Orders, inventory, fulfilment  `[x] 7/7`
- [x] Orders list with backorder / late flags
- [x] Allocation view — per-line split bars + the backend's own explanation
- [x] Multi-warehouse split verified live: 60 Main / 40 East, 2 shipments, $420
- [x] Backorder rendering (verified when stock was genuinely exhausted)
- [x] Fulfil and confirm-delivery
- [x] Inventory with reorder-point highlighting
- [x] Warehouses CRUD (priority drives the split)

## Phase 9 — Billing  `[x] 6/6`
- [x] Schedules with one-time vs recurring as the primary axis
- [x] Order billing summary — verified 3 one-time + 1 yearly
- [x] Invoices, issue, record payment, void
- [x] Subscriptions (five real statuses — no fabricated "Paused")
- [x] Subscription change / cancel with the proration result rendered
- [x] Credit notes

## Phase 10 — Intelligence  `[x] 5/5`
- [x] Deal Health — score, band, expandable per-signal point deductions
- [x] Attention items — 11 types with why / impact / do, and all four actions
- [x] Anomalies — per-rep sigma with the baseline explained
- [x] Activity — append-only audit, newest-first, paginated
- [x] Command Center integration

## Phase 11 — Administration + reporting  `[x] 8/8`
- [x] Products CRUD with live margin preview
- [x] Price lists + variants (honest empty states — these seed empty)
- [x] Policies — discount ceilings and approval chains as one screen
- [x] Warehouses
- [x] Governance settings — risk weights, thresholds, SLA, anomaly sigma
- [x] Sales teams · Users
- [x] 5 reports with charts
- [x] Export csv / xlsx / pdf (binary, honours `Content-Disposition`)

## Phase 12 — Integration and QA  `[x] 8/9`
- [x] **Canonical journey passes through the UI** against the real backend:
      login → build → policy → submit → manager → finance → send → counter →
      material change → stale → blocked → re-approval → confirm → order →
      allocate → fulfil → billing → audit → deal health
- [x] Visual QA — 31 routes captured at 1280×720, 1440×900, 1920×1080
- [x] Zero console errors asserted across every screen
- [x] Zero horizontal overflow asserted at 1280×720
- [x] Typecheck, lint, unit tests, production build all clean
- [x] Error, empty, loading and permission states implemented throughout
- [x] Keyboard-operable tables, labelled inputs, `role="alert"` errors, focus rings
- [x] Route-level code splitting; charts kept off the critical path
- [ ] AccessLint WCAG 2.2 AA sweep — **not yet run**

---

## Bugs found and fixed during the frontend build

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Every page using `Button asChild` crashed to the error boundary | Radix `Slot` received the icon *and* the child, and requires exactly one | Wrapped the child in `Slottable` |
| 2 | React key warning on the quote detail | `/quote-versions/{id}/approval` returns a **trimmed** approval whose steps have **no `id`** — my declared type was wrong, so `key={s.id}` was `undefined` | Declared the real trimmed shape; keyed by `sequence` |
| 3 | Activity feed showed the oldest events first | The API's `newest_first` parameter was not being used | Newest-first by default, with a toggle |
| 4 | Impact page printed raw JSON for affected entities | Rendered `JSON.stringify` instead of the `{type, reason}` fields | Rendered the fields |
| 5 | `size="sm"` silently typed as `undefined` on inputs | `HTMLInputElement` already has `size?: number`; intersecting collapsed it to `undefined` | Omitted `size` from the base attribute type |

Nothing was worked around in the UI — each was fixed at its source.

---

## Anti-fake ledger — all enforced

- [x] No business number computed client-side; totals always from the API
- [x] No `parseFloat` / `Number()` on API values in feature code — **ESLint-enforced**;
      the one legitimate float path is the named `sortKey()` used only by comparators
- [x] No hardcoded revenue, margin, risk, inventory or threshold anywhere
- [x] No UI for absent capabilities (`docs/FEATURE_GAP_MATRIX.md` §C)
- [x] No fabricated states — the wireframe's "Paused" subscription and "Weekly"
      interval are **not** offered, because the backend enums have neither
- [x] No fake liveness — nothing pulses to imply a push channel that doesn't exist
- [x] Portal isolation asserted by a CI test, not by convention

## Known limits

- Deals and Customers are list-only; no detail pages yet.
- Manual allocation override is accepted by the API but not exposed in the UI;
  allocation is automatic plus `allow_partial` on shortage.
- Tablet and phone breakpoints are handled by the shell and tables scroll
  horizontally, but layouts below 1024px have not been visually audited.
- AccessLint has not been run; accessibility work so far is by construction
  (semantic tables, labelled inputs, Radix focus management, visible focus rings).
