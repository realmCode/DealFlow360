# FRONTEND_ARCHITECTURE

## Constraints this design answers

Drawn from Phase 0 verification, not from preference.

1. **The backend is authoritative.** Totals, margin, risk, routing, and
   staleness are computed server-side. The client renders; it never derives a
   business number.
2. **Money is a JSON string** with fixed precision — amounts 2dp, unit prices
   4dp, percentages 4dp, quantities 4dp, proration 8dp. `Number("132710.00")`
   is a bug.
3. **Two disjoint applications** behind one login. `is_internal` decides.
   The customer must never receive cost, margin, risk, or internal reasoning.
4. **Errors are a typed vocabulary**, not strings. ~120 codes in one envelope;
   `STALE_APPROVAL` and friends are product features that need designed UI.
5. **No push channel.** No WebSocket, no SSE. Freshness is refetch-driven.
6. **Two shapes of list response**: a `Page{items,total,limit,offset}` envelope
   for large collections, bare arrays for reference collections. Verified per
   endpoint.
7. **Idempotency is required** on order confirmation and stock allocation.

---

## Stack

| Concern | Choice | Why |
|---|---|---|
| Build | **Vite + React 19 + TypeScript (strict)** | The backend already whitelists `http://localhost:5173` in CORS — Vite is the intended client |
| Routing | **React Router 7** (data router) | Two route trees, loader-level role gating, deep-linkable table state |
| Server state | **TanStack Query v5** | Caching, invalidation, focus refetch, request dedup — §26's requirements are its feature list |
| Forms | **React Hook Form + Zod** | `shadcn` stack CSV marks the Form+RHF+Zod pattern Severity: High |
| Tables | **TanStack Table** headless + own renderer | Sorting/filtering/pagination without inheriting a look |
| Components | **Radix primitives**, styled in-house | Accessible dialog/popover/tabs focus management for free, no default shadcn appearance (§9) |
| Styling | **Tailwind v3 + CSS custom properties** | Tokens live in CSS vars so semantic colour is themable and inspectable |
| Charts | **Recharts** | Top-rated in `charts.csv` for the five chart types needed |
| Money | **decimal.js-light** | Non-negotiable given constraint 2 |
| Client state | **Zustand** (auth session only) | Everything else is server state |
| Motion | **CSS + View Transition API** | No animation library; §26 forbids unnecessary deps |
| Icons | **Lucide** | `icons.csv` is Lucide-based; no emoji icons |
| Tests | **Vitest + Testing Library + Playwright** | Playwright also drives visual and responsive QA |

Deliberately excluded: shadcn CLI (generates the default look §9 forbids — the
CSV *guidance* is used, the generated components are not), GSAP, daisyUI, any
component kit with an opinionated visual identity.

---

## Layout

```
frontend/
├── src/
│   ├── api/
│   │   ├── generated/types.ts     openapi-typescript from docs/openapi.json
│   │   ├── client.ts              fetch wrapper: auth, refresh, error normalisation
│   │   ├── errors.ts              DealFlowError + the code catalogue
│   │   ├── money.ts               Decimal parse/format — the ONLY numeric conversion
│   │   └── resources/             one module per tag: quotes, approvals, orders…
│   ├── app/
│   │   ├── router.tsx             two route trees
│   │   ├── guards.tsx             role gating (UX only — the server is the boundary)
│   │   └── providers.tsx
│   ├── design-system/
│   │   ├── tokens.css             the semantic tokens from UIUX_SKILLS_MAP
│   │   └── primitives/            Button, Input, Table, Badge, Drawer, Dialog,
│   │                              Timeline, Stepper, Skeleton, EmptyState,
│   │                              ErrorState, Money, Percent, RiskBadge,
│   │                              StatusBadge, PolicyChip
│   ├── features/                  one folder per domain, co-located
│   │   ├── auth/ command-center/ quotes/ quote-builder/ approvals/
│   │   ├── impact/ negotiation/ orders/ inventory/ billing/
│   │   ├── intelligence/ admin/ reports/ portal/
│   ├── shells/
│   │   ├── InternalShell.tsx      dense navy console
│   │   └── PortalShell.tsx        deliberately different: lighter, wider, calmer
│   └── lib/
└── e2e/                           Playwright: the canonical journey
```

`features/` is the unit of ownership: each folder holds its routes, components,
queries, and tests. No shared "components/" dumping ground.

---

## The API layer

### Types are generated, never written

```bash
npx openapi-typescript ../docs/openapi.json -o src/api/generated/types.ts
```

187 schemas. Hand-writing them would guarantee drift; the spec is verified
identical to the live server, so generation is safe.

### One client

`client.ts` is the only place that calls `fetch`. It:

- attaches `Authorization: Bearer`
- refreshes **once** on 401 `AUTHENTICATION_FAILED`, sharing a single in-flight
  refresh promise across concurrent 401s; does **not** retry
  `WRONG_TOKEN_TYPE`, `USER_DISABLED`, `ORGANIZATION_DISABLED`
- normalises every non-2xx into `DealFlowError { code, message, details, status }`
- unwraps `Page` envelopes behind a typed helper
- passes `Idempotency-Key` through
- returns `Blob` for exports, honouring `Content-Disposition`

Components never see a raw `Response`. There are no scattered `fetch` calls.

### Money

```ts
// The only module permitted to convert an API numeric string.
export const money = (v: string) => new Decimal(v);
export const formatMoney = (v: string, currency = "USD") => …  // 2dp, grouped
export const formatPct    = (v: string) => …                   // 4dp → 2dp display
export const formatQty    = (v: string) => …                   // trailing zeros trimmed
```

A lint rule bans `parseFloat`, `Number(`, and `+` coercion inside `features/`.
Display uses `<Money value={…}/>` and `<Percent value={…}/>`, which apply
tabular numerals.

### Query conventions

Keys mirror routes: `["quotes", { page, filters }]`, `["quote-version", id]`.
After a mutation, invalidate the specific entity plus `control-tower` and
`attention-items`, because most mutations change the action queue.

Polling: **only** Control Tower and approval inbox, 45 s, and only while
`document.visibilityState === "visible"`. Everything else refetches on focus and
after mutation. A quote being edited is never polled.

Optimistic updates: only `POST …/recommendations/{id}/dismiss`. Every other
mutation changes server-computed money and must round-trip.

---

## Error handling as product surface

A generic toast is a design failure here. Codes map to designed responses:

| Code | Response |
|---|---|
| `STALE_APPROVAL` | Full-screen state on the quote — *"This quotation changed after approval. The previous approval is no longer valid."* with **Review changes** → `/impact` and **Request re-approval**. Never a toast |
| `IMMUTABLE_VERSION`, `VERSION_NOT_DRAFT` | Inline: editing is disabled; offer **Create revision** |
| `APPROVAL_REQUIRED` | Show `details.awaiting[]` — who is blocking, by name |
| `SELF_APPROVAL_FORBIDDEN` | Explain the separation-of-duties rule; don't render the button for the author in the first place |
| `INSUFFICIENT_INVENTORY` | Show the shortfall and offer **Allocate partially** (`allow_partial`) |
| `ALREADY_CONFIRMED`, `DUPLICATE_OPERATION` | Treat as **success** and refetch |
| `IDEMPOTENT_REQUEST_IN_FLIGHT` | Retry the same key after ~1 s, keep the spinner |
| `IDEMPOTENCY_KEY_REUSED` | Fresh key, resubmit |
| `FORBIDDEN` | Use `details.your_role` / `allowed_roles` to say who *can* do it |
| `NOT_FOUND` | Plain not-found. Cross-tenant returns 404 by design — never say "permission denied" |
| `VALIDATION_ERROR` | Map `details.errors[].loc` onto form fields via RHF `setError` |
| `RATE_LIMITED` | Countdown from `details.retry_after_seconds` |

Every list and detail view implements the seven states from §25: loading
(skeleton, not spinner), empty (with the action that fills it), error (with
retry), success, disabled, permission-denied, and conflict/stale.

---

## Role-aware UX

`GET /users/me` drives the shell. Route guards are **UX affordances** — the
server is the security boundary, and the UI is written to survive a 403 from
any call.

| Role | Landing | Navigation emphasis |
|---|---|---|
| SALES | Command Center → `my_queue` | Quotes, builder, negotiation, pipeline |
| MANAGER | Approval inbox | Approvals, team performance, discounts |
| FINANCE | Financial exposure | Approvals, invoices, subscriptions, margin |
| OPS | Fulfilment queue | Orders, allocation, inventory, backorders |
| ADMIN | Governance | Policies, settings, users, catalogue |
| CUSTOMER | **Portal shell** | Own quotes and negotiation only |

These are different *default views and ordering* over shared components, not
six bespoke dashboards.

---

## The customer portal is a different product

Not a themed variant: separate shell, separate layout language.

Lower density, wider measure, larger type, generous whitespace, no sidebar —
a proposal to read rather than a console to operate. It answers: here is your
proposal · what you are buying · the terms · what changed · what you can request
· how you confirm.

Enforcement is structural, not conditional: the portal imports only from
`api/resources/portal.ts`, whose types are the portal schemas. Cost, margin, and
risk fields do not exist on those types, so referencing one is a compile error
rather than a leak. A Playwright test asserts no forbidden key appears in any
portal network response.

---

## Performance

Route-level code splitting; charts, export dialog, and the diff view lazy.
Parallel fetches per `react-best-practices` `async-*` — the quote detail issues
version, policy-results, impact, approval, and recommendations concurrently.
`content-visibility: auto` on long table bodies; `useDeferredValue` for filter
input; server-side pagination wherever the `Page` envelope exists. Budget: under
200 KB gzipped for the initial internal route.

---

## Verification loop

Per §32, run after every screen — not once at the end:

```bash
pnpm typecheck && pnpm lint && pnpm test        # unit
pnpm build                                       # production build must pass
pnpm e2e                                         # Playwright, real backend
node SKILLS_ALL/ui-ux-pro-max-skill/stack/scripts/design-audit.mjs \
     --url http://localhost:5173/<route>         # 6 viewports, overflow/focus/contrast
npx @accesslint/cli scan http://localhost:5173/<route>   # WCAG 2.2 AA
```

Playwright captures 1280×720, 1440×900, and 1920×1080 for every major screen so
"visual QA" means inspecting a rendered artifact, and asserts a clean browser
console.

E2E runs against the **real** backend on `:8010` with the seeded tenant, walking
the canonical journey from `REFERENCE_TO_FRONTEND_MAP.md` and asserting the
values the API returns — never hardcoded constants.
