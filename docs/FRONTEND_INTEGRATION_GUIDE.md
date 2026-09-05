# FRONTEND INTEGRATION GUIDE

Companion to [`BACKEND_API_DOCUMENTATION.md`](./BACKEND_API_DOCUMENTATION.md).
That document says what the API returns; this one says how to consume it
without repeating the mistakes the API is designed to prevent.

Base URL: `http://127.0.0.1:8000`. Spec: [`openapi.json`](./openapi.json).

---

## 1. Five rules that shape the whole client

Everything below follows from these. Getting them wrong produces bugs that
look like backend faults.

### 1.1 Money is a string. Never `parseFloat` it.

```json
{ "net_revenue": "132710.00", "margin_pct": "24.4970" }
```

The backend serialises every monetary and percentage value as a JSON string
precisely so a JavaScript client cannot silently lose cents to IEEE-754.
Parsing with `Number()` reintroduces the bug the encoding exists to prevent.

```ts
import Decimal from "decimal.js";

// Correct
const revenue = new Decimal(version.net_revenue);

// Wrong — 0.1 + 0.2 problems, in front of a customer
const revenue = parseFloat(version.net_revenue);
```

Keep money as `Decimal` (or as the original string) all the way to the
formatter. Format for display only:

```ts
export function formatMoney(value: string, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency, minimumFractionDigits: 2,
  }).format(new Decimal(value).toNumber());   // safe: display only
}
```

### 1.2 Never compute a total, margin, discount or risk score

The backend is the sole authority. Client-side arithmetic will disagree with
the server the moment rounding, tax, an order-level discount or a recurring
period is involved — and the server's number is the one that gets approved and
invoiced.

After any line change, call `POST /quote-versions/{id}/calculate` and render
what comes back. That endpoint returns the **entire** version, so one request
refreshes every figure on the screen. This is also what makes PDF B5's
"margin indicator updates immediately" true rather than approximate.

### 1.3 Branch on `error.code`, never on `error.message`

```ts
if (err.code === "STALE_APPROVAL") showReapprovalNotice();
```

`code` is the stable contract. `message` is prose written for humans and may
be reworded. Most messages are safe to display verbatim — that is deliberate.

### 1.4 `details` is a payload, not decoration

The error envelope carries machine-usable context the UI should actually use:

| Error | Useful `details` | Use it to |
|---|---|---|
| `FORBIDDEN` | `your_role`, `allowed_roles` | Name the roles that can do this |
| `IMMUTABLE_VERSION` | `status`, `editable_statuses` | Offer "Create revision" |
| `WRONG_APPROVER_ROLE` | `required_role`, `your_role` | Explain whose turn it is |
| `NO_PENDING_STEP` | `already_decided[]` | Show what was already decided |
| `APPROVAL_REQUIRED` | `awaiting[]` | List the outstanding approvers |
| `INSUFFICIENT_INVENTORY` | quantities, warehouse | Show the shortfall |
| `OVERPAYMENT` | `amount_due` | Prefill the correct amount |
| `VALIDATION_ERROR` | `errors[].loc` | Attach messages to fields |
| `RATE_LIMITED` | `retry_after_seconds` | Count down the button |
| `PORTAL_USER_FORBIDDEN` | `use_instead` | Redirect to the right shell |

### 1.5 Two shells, one API

`GET /users/me` returns `is_internal`. Route on it:

- `is_internal: true` → workspace + config area (`/products`, `/deals`, `/quotes`, `/approvals`, `/orders`, `/billing`, `/dashboard`, `/reports`, `/admin`)
- `is_internal: false` (role `CUSTOMER`) → portal only (`/portal/*`)

These are mutually exclusive and enforced server-side in both directions. A
customer hitting an internal route gets 403 `PORTAL_USER_FORBIDDEN`; an
employee hitting `/portal/*` gets 403 `INTERNAL_USER_FORBIDDEN`. Build them as
separate route trees, not one tree with conditionals.

---

## 2. API client architecture

```
src/
  api/
    client.ts            # fetch wrapper: auth, error envelope, refresh, Page<T>
    errors.ts            # ApiError, ErrorCode union, isCode() guard
    types.ts             # generated from openapi.json — do not hand-edit
    enums.ts             # hand-written enum unions + display labels
    endpoints/
      auth.ts            # login, signup, refresh, me
      admin.ts           # products, variants, price lists, warehouses,
                         # inventory, policies, settings, sales teams, seed
      catalog.ts         # products, policies, warehouses, inventory
      customers.ts
      deals.ts
      quotes.ts          # list, detail, lines, calculate, discount,
                         # policy-results, simulate, submit, revise, send,
                         # recommendations, lose
      approvals.ts       # inbox, detail, approve/reject/request-revision
      portal.ts          # customer-facing only
      orders.ts          # list, detail, allocate, fulfill, promise,
                         # deliver, cancel
      billing.ts         # schedules, summary, proration, invoices, payments,
                         # subscriptions, credit notes
      dashboard.ts       # control tower, attention items + actions,
                         # deal health, audit
      reports.ts         # five reports + anomalies + binary export
  hooks/                 # one hook per resource, wrapping the endpoint module
  stores/
    auth.ts              # tokens, current user, role helpers
```

Two rules for this layer. Nothing outside `src/api/` calls `fetch` — otherwise
error handling and token refresh get reimplemented inconsistently. And
`types.ts` is generated, never edited, so it cannot drift from the server.

### Generate the types

```bash
npx openapi-typescript docs/openapi.json -o src/api/types.ts
```

Regenerate whenever the backend changes. To pull from a running server
instead:

```bash
npx openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api/types.ts
```

---

## 3. The client wrapper

```ts
// src/api/errors.ts
export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Field-level messages from a 422, keyed by dotted field path. */
  fieldErrors(): Record<string, string> {
    const raw = this.details?.errors;
    if (!Array.isArray(raw)) return {};
    const out: Record<string, string> = {};
    for (const e of raw as Array<{ loc?: unknown[]; msg?: string }>) {
      // loc is ["body", "email"] or ["body", "lines", 0, "quantity"].
      // Drop the "body"/"query"/"path" prefix to get the form path.
      const path = (e.loc ?? []).slice(1).join(".");
      if (path && e.msg) out[path] = e.msg;
    }
    return out;
  }
}
```

```ts
// src/api/client.ts
import { ApiError } from "./errors";
import { auth } from "../stores/auth";

const BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

interface Options extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, unknown>;
  idempotencyKey?: string;
  /** Internal: prevents an infinite refresh loop. */
  _retried?: boolean;
}

function buildQuery(query?: Record<string, unknown>): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    // Omit empty filters entirely; the backend treats absent as "no filter",
    // and sending "" would be a validation error on typed parameters.
    if (value === undefined || value === null || value === "") continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { body, query, idempotencyKey, _retried, ...init } = options;

  const headers = new Headers(init.headers);
  const token = auth.accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);

  const response = await fetch(`${BASE}${path}${buildQuery(query)}`, {
    ...init,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // 204: DELETE a quote line, dismiss a recommendation.
  if (response.status === 204) return undefined as T;

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const err = payload?.error ?? {};
    const error = new ApiError(
      response.status,
      err.code ?? "UNKNOWN",
      err.message ?? response.statusText,
      err.details ?? {},
      Number(response.headers.get("Retry-After")) || undefined,
    );

    // One silent refresh attempt, then give up. WRONG_TOKEN_TYPE and
    // USER_DISABLED are not fixable by refreshing.
    if (
      response.status === 401 &&
      error.code === "AUTHENTICATION_FAILED" &&
      !_retried &&
      auth.refreshToken()
    ) {
      const refreshed = await auth.tryRefresh();
      if (refreshed) return request<T>(path, { ...options, _retried: true });
    }
    if (response.status === 401) auth.logout();
    throw error;
  }

  return response.json() as Promise<T>;
}

export const api = {
  get:   <T>(p: string, o?: Options) => request<T>(p, { ...o, method: "GET" }),
  post:  <T>(p: string, body?: unknown, o?: Options) =>
           request<T>(p, { ...o, method: "POST", body: body ?? {} }),
  patch: <T>(p: string, body?: unknown, o?: Options) =>
           request<T>(p, { ...o, method: "PATCH", body }),
  del:   <T>(p: string, o?: Options) => request<T>(p, { ...o, method: "DELETE" }),
};
```

**Note the `POST` default of `{}`.** Several endpoints (`submit`, `send`,
`allocate`, `calculate`) take an optional body but the route still declares
one; sending no body at all yields a 422 on some of them. Defaulting to `{}`
removes a whole class of confusing failures.

### Binary export needs a different path

`GET /reports/{name}/export` returns a file, not JSON, so it cannot go through
`request()`:

```ts
export async function downloadReport(
  report: string,
  format: "csv" | "xlsx" | "pdf",
  query: Record<string, unknown> = {},
): Promise<void> {
  const res = await fetch(
    `${BASE}/reports/${report}/export${buildQuery({ ...query, format })}`,
    { headers: { Authorization: `Bearer ${auth.accessToken()}` } },
  );
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new ApiError(res.status, payload?.error?.code ?? "EXPORT_FAILED",
                       payload?.error?.message ?? "Export failed");
  }

  // Prefer the server's filename; it carries a timestamp.
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? `${report}.${format}`;

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
```

`Content-Disposition` is CORS-exposed by the backend specifically so this
works.

---

## 4. Authentication state

### Where to store the token

Use **`sessionStorage` for the access token and in-memory for the refresh
token**, or keep both in memory with a refresh-on-load flow.

Do **not** move to cookies without also changing the backend CORS
configuration. The API authenticates with an `Authorization` header and
`cors_allow_credentials` is deliberately off; switching to cookies without
pinning origins would reintroduce the finding recorded as SEC-2 in
[`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md).

`localStorage` is the common choice and is acceptable here — the token is a
60-minute bearer with no cookie-based CSRF surface — but it is readable by any
XSS, so prefer `sessionStorage` unless "stay signed in across tabs" is a
requirement.

### Store shape

```ts
interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthenticatedUser | null;   // from login, or GET /users/me
  status: "unknown" | "authenticated" | "anonymous";
}
```

`status: "unknown"` is what prevents a flash of the login screen on reload
while `/users/me` is still in flight. Render a splash until it resolves.

### Login

```ts
const { tokens, user } = await api.post<LoginResponse>("/auth/login", {
  email, password,
});
auth.set({
  accessToken: tokens.access_token,
  refreshToken: tokens.refresh_token,
  user,
  status: "authenticated",
});
// tokens.expires_in is seconds (3600). Schedule a proactive refresh at ~90%.
scheduleRefresh(tokens.expires_in * 0.9 * 1000);
```

`login` already returns the user, so no second call is needed. On reload,
call `GET /users/me` — it re-reads the row server-side, so a role change or
deactivation is reflected immediately.

### Refresh

```ts
async function tryRefresh(): Promise<boolean> {
  const token = auth.refreshToken();
  if (!token) return false;
  try {
    const pair = await api.post<TokenPair>("/auth/refresh", {
      refresh_token: token,
    });
    auth.setTokens(pair.access_token, pair.refresh_token);
    return true;
  } catch {
    auth.logout();      // refresh is stateless; a failure is terminal
    return false;
  }
}
```

Guard against a refresh stampede: if several requests 401 at once, they must
share one in-flight refresh promise rather than each firing their own.

```ts
let inflight: Promise<boolean> | null = null;
export function tryRefreshOnce(): Promise<boolean> {
  inflight ??= tryRefresh().finally(() => { inflight = null; });
  return inflight;
}
```

### Logout

There is **no logout endpoint** — tokens are stateless. Clear local state and
redirect. Be honest in the UI: this ends the session on this device only.

### Protected and role-based routes

```ts
const ROLE_HOME: Record<Role, string> = {
  SALES:    "/workspace/quotes",
  MANAGER:  "/approvals",
  FINANCE:  "/approvals",
  OPS:      "/orders",
  ADMIN:    "/admin",
  CUSTOMER: "/portal",
};

// Route guards mirror the server's dependencies, which are the real gate.
export const CAN = {
  authorQuotes:  ["SALES", "MANAGER", "ADMIN"],
  approve:       ["MANAGER", "FINANCE", "ADMIN"],
  allocateStock: ["OPS", "SALES", "ADMIN"],
  fulfill:       ["OPS", "ADMIN"],
  billing:       ["FINANCE", "ADMIN"],
  administer:    ["ADMIN"],
} as const;
```

**Hiding a button is UX, not security.** Every one of these is enforced
server-side; the client copy exists to avoid showing an action that will fail.
Never rely on it, and never treat a 403 as a bug — render it.

---

## 5. Error handling map

| Status / code | UI behaviour |
|---|---|
| **401** `AUTHENTICATION_FAILED` | Silent refresh once; if that fails, redirect to login preserving the return path |
| **401** `WRONG_TOKEN_TYPE` | Clear state and log out — a client bug, not recoverable |
| **401** `USER_DISABLED` / `ORGANIZATION_DISABLED` | Log out with the message shown; do not retry |
| **403** `FORBIDDEN` | Permission screen naming `details.allowed_roles` |
| **403** `PORTAL_USER_FORBIDDEN` | Redirect to `details.use_instead` (`/portal/*`) |
| **403** `INTERNAL_USER_FORBIDDEN` | Redirect to the internal workspace |
| **403** `SELF_APPROVAL_FORBIDDEN` | Inline: "You authored this quote, so you cannot approve it." Disable the buttons |
| **403** `WRONG_APPROVER_ROLE` | "Waiting on `details.required_role`." Show the step order |
| **403** `NOT_ITEM_OWNER` | Disable resolve/acknowledge; explain `details.owner_role` owns it |
| **404** `NOT_FOUND` | Not-found state. **Also means cross-tenant** — never say "you lack permission", the 404 is deliberate so ids cannot be probed |
| **409** `IMMUTABLE_VERSION` | Show the message and offer "Create revision" as the primary action |
| **409** `VERSION_TERMINAL` | Read-only banner: this version can never change |
| **409** `STALE_APPROVAL` | Prominent notice with `details.version_number`. Internally: "re-approval required". In the portal: show `blocked_reason` verbatim |
| **409** `APPROVAL_REQUIRED` | List `details.awaiting[]` |
| **409** `NO_PENDING_STEP` / `APPROVAL_NOT_PENDING` | Refetch and show what was already decided — someone else acted first |
| **409** `ALREADY_CONFIRMED` / `DUPLICATE_OPERATION` | **Treat as success.** Refetch and show the existing order |
| **409** `IDEMPOTENCY_KEY_REUSED` | Client bug: a key was reused with a different body. Generate a fresh key |
| **409** `IDEMPOTENT_REQUEST_IN_FLIGHT` | Keep the spinner, retry after ~1s with the same key |
| **409** `INSUFFICIENT_INVENTORY` | Show the shortfall; offer `allow_partial: true` |
| **409** `PERIOD_ALREADY_INVOICED` | Explain invoiced periods are immutable; suggest cancelling instead |
| **409** `*_EXISTS` | Field-level "already taken" on the relevant input |
| **422** `VALIDATION_ERROR` | Map `details.errors[].loc` to fields via `fieldErrors()` |
| **422** `INVALID_SORT_FIELD` / `INVALID_GROUP_BY` | Developer error; fall back to the default and log |
| **422** `PERIOD_RANGE_REQUIRED` / `INVALID_PERIOD_RANGE` | Inline date-picker validation |
| **429** `RATE_LIMITED` | Disable the submit button and count down `details.retry_after_seconds` |
| **500** `INTERNAL_ERROR` | Recoverable error state with a Retry button. Never a blank screen |
| Network failure | Distinguish from HTTP errors. Offer retry; for `confirm`/`allocate` retry **with the same `Idempotency-Key`** |

### The two 409s that are really successes

`ALREADY_CONFIRMED` and `DUPLICATE_OPERATION` mean the thing you wanted has
already happened. Refetch and show the result — surfacing them as failures
makes the app look broken after a double-click.

---

## 6. Idempotency

Two endpoints accept `Idempotency-Key`: `POST /portal/quotes/{id}/confirm` and
`POST /orders/{id}/allocate`.

Generate the key **once per user intent**, not per attempt, and keep it for
the whole retry sequence:

```ts
const [idemKey] = useState(() => crypto.randomUUID());  // stable per mount

async function confirm() {
  try {
    const res = await api.post<ConfirmResponse>(
      `/portal/quotes/${quoteId}/confirm`,
      { acceptance_note: note },
      { idempotencyKey: idemKey },
    );
    // Identical whether this was the first call or a replay.
    if (res.idempotent_replay) toast("This quote was already confirmed.");
    showOrder(res.order);
  } catch (e) {
    if (e instanceof ApiError && e.code === "IDEMPOTENT_REQUEST_IN_FLIGHT") {
      await sleep(1000);
      return confirm();               // same key
    }
    throw e;
  }
}
```

Regenerating the key on retry defeats the protection and can create two
orders — except that the database's `UNIQUE (sales_orders.quote_version_id)`
still prevents it, which is why a duplicate returns the existing order rather
than an error. Do not rely on that backstop; send the key.

---

## 7. Loading, empty and error states

### Initial load (skeletons)

| Screen | Requests | Notes |
|---|---|---|
| App boot | `GET /users/me` | Splash while `status === "unknown"` |
| Quotations list | `GET /quotes` | Table skeleton, 5 rows |
| Pipeline board | `GET /deals?stage=…` | Column skeletons; one request per column, or one unfiltered request grouped client-side |
| Quote builder | `GET /quote-versions/{id}` + `GET /products` | Load in parallel |
| Approval inbox | `GET /approvals/inbox` | Card skeletons |
| Approval detail | `GET /approvals/{id}` | Show `financials` prominently |
| Control Tower | `GET /dashboard/control-tower` | Skeleton per severity group |
| Portal quote | `GET /portal/quotes/{id}` | |
| Reports | `GET /reports/{name}` | Chart skeleton |

### Button loading (mutations)

Disable and spin for: add/update/delete line, calculate, set discount, submit,
create revision, send, approve/reject/return, confirm, allocate, fulfill,
deliver, cancel, invoice, record payment, subscription change/cancel, refund,
resolve/acknowledge/nudge/escalate, every admin create/update, export.

Disabling matters beyond aesthetics: a double-click on submit produces a 409
that has to be handled anyway.

### Optimistic updates: don't

The one thing to avoid. Adding a quote line changes the totals, the effective
discount, the blended risk score and the required approvers — none of which
the client can predict. Wait for the response and render it.

The exception is a pure toggle with no derived state, such as dismissing a
recommendation (`204`).

### Empty states worth writing properly

| Condition | Message |
|---|---|
| No quotes | "No quotations yet. Create a deal to get started." + CTA |
| No deals in a stage | Quiet column placeholder, not an error |
| Empty approval inbox | "Nothing waiting on you." — a genuinely good outcome |
| Control Tower clear | Use the server's `headline`: *"Nothing needs your attention. Every deal is inside policy."* |
| No recommendations | Hide the panel rather than showing an empty box |
| No portal quotes | "No quotations have been shared with you yet." |
| Report with no data | "No data matched these filters." + a reset action |
| No anomalies | "No unusual discounting detected." |

### Retry

Idempotent `GET`s: retry automatically up to 2 times with backoff on network
failure or 500. Mutations: never retry automatically except
`IDEMPOTENT_REQUEST_IN_FLIGHT`; show a Retry button instead.

---

## 8. TypeScript models

Generate these from `openapi.json`. The list below is what you should expect to
find, so a mismatch is easy to spot.

### Enums (hand-write these as unions with display labels)

```ts
export type Role = "SALES" | "MANAGER" | "FINANCE" | "OPS" | "CUSTOMER" | "ADMIN";
export type CustomerTier = "BRONZE" | "SILVER" | "GOLD" | "PLATINUM";
export type PaymentTerms =
  | "PREPAID" | "NET_15" | "NET_30" | "NET_45" | "NET_60" | "NET_90";
export type ProductCategory =
  | "HARDWARE" | "SOFTWARE" | "SERVICE" | "SUBSCRIPTION";
export type BillingType = "ONE_TIME" | "RECURRING";
export type RecurringInterval = "MONTHLY" | "QUARTERLY" | "YEARLY";
export type DealStage =
  | "QUALIFICATION" | "PROPOSAL" | "NEGOTIATION" | "CLOSED_WON" | "CLOSED_LOST";
export type QuoteStatus = "OPEN" | "CONFIRMED" | "LOST" | "CANCELLED";
export type QuoteVersionStatus =
  | "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "SENT"
  | "NEGOTIATING" | "CONFIRMED" | "REJECTED" | "SUPERSEDED";
export type RiskBand = "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ApprovalLevel = "SALES_MANAGER" | "FINANCE" | "EXECUTIVE";
export type ApprovalRequestStatus =
  | "PENDING" | "APPROVED" | "REJECTED"
  | "REVISION_REQUESTED" | "STALE" | "CANCELLED";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type SalesOrderStatus =
  | "CREATED" | "ALLOCATED" | "PARTIALLY_ALLOCATED" | "BACKORDERED"
  | "PARTIALLY_FULFILLED" | "FULFILLED" | "CANCELLED";
export type InvoiceStatus =
  | "DRAFT" | "ISSUED" | "PARTIALLY_PAID" | "PAID" | "OVERDUE" | "VOID";

/** Money and percentages arrive as strings. Alias for intent. */
export type Money = string;
export type Percent = string;
```

Some enum values are unreachable through the API — see
[`ENTITY_STATE_LIFECYCLES.md`](./ENTITY_STATE_LIFECYCLES.md) §15 before
designing UI for `OVERDUE`, `PICKED`, or `EXECUTIVE`.

### Core interfaces

```ts
export interface AuthenticatedUser {
  id: string; email: string; full_name: string; role: Role;
  organization_id: string; organization_name: string;
  organization_kind: "SELLER" | "CUSTOMER";
  is_internal: boolean;
}

export interface TokenPair {
  access_token: string; refresh_token: string;
  token_type: "bearer"; expires_in: number;   // seconds
}

export interface QuoteListItem {
  quote_id: string; quote_number: string; title: string; status: QuoteStatus;
  deal_id: string; deal_reference: string; deal_stage: DealStage;
  customer_profile_id: string; customer_display_name: string | null;
  customer_tier: CustomerTier | null;
  current_version_id: string | null; current_version_number: number;
  current_version_status: QuoteVersionStatus | null;
  total_revenue: Money; net_revenue: Money;
  margin_pct: Percent; effective_discount_pct: Percent;
  blended_risk_score: Percent; risk_band: RiskBand | null;
  requires_approval: boolean; is_stale: boolean;
  owner_user_id: string; owner_name: string | null;
  line_count: number; version_count: number;
  age_days: number; last_activity_at: string; created_at: string;
}

export interface QuoteLine {
  id: string; quote_version_id: string; product_id: string;
  product_variant_id: string | null;
  line_number: number; description: string; category: ProductCategory;
  quantity: string;
  unit_list_price: Money; unit_cost: Money; unit_net_price: Money;
  discount_pct: Percent; discount_amount: Money;
  order_discount_amount: Money; effective_discount_pct: Percent;
  gross_amount: Money; net_amount: Money;
  tax_rate_pct: Percent; tax_amount: Money; total_amount: Money;
  line_cost: Money; line_margin: Money; line_margin_pct: Percent;
  billing_type: BillingType; recurring_interval: RecurringInterval | null;
  recurring_periods: number; is_stock_tracked: boolean;
  notes: string | null; created_at: string; updated_at: string;
}

export interface QuoteVersion {
  id: string; quote_id: string; version_number: number;
  parent_version_id: string | null;
  status: QuoteVersionStatus; source: string;
  revision_reason: string | null; created_by_user_id: string;
  currency: string; payment_terms: PaymentTerms; valid_until: string | null;
  order_discount_pct: Percent; order_discount_amount: Money;
  gross_revenue: Money; total_discount: Money; net_revenue: Money;
  tax_amount: Money; total_revenue: Money; total_cost: Money;
  margin: Money; margin_pct: Percent; effective_discount_pct: Percent;
  one_time_revenue: Money; recurring_revenue: Money;
  blended_risk_score: Percent; risk_band: RiskBand;
  requires_approval: boolean; is_stale: boolean; stale_reason: string | null;
  calculated_at: string | null; submitted_at: string | null;
  approved_at: string | null; sent_at: string | null;
  confirmed_at: string | null; rejected_at: string | null;
  superseded_at: string | null;
  is_editable: boolean;                       // gate line editing on this
  lines: QuoteLine[];
  created_at: string; updated_at: string;
}

/** Portal view. Note what is structurally absent. */
export interface QuoteLinePublic {
  id: string; product_id: string; line_number: number;
  description: string; category: ProductCategory;
  quantity: string;
  unit_list_price: Money; unit_net_price: Money;
  discount_pct: Percent; discount_amount: Money;
  effective_discount_pct: Percent;
  gross_amount: Money; net_amount: Money;
  tax_amount: Money; total_amount: Money;
  billing_type: BillingType; recurring_interval: RecurringInterval | null;
  recurring_periods: number;
  // No unit_cost, line_cost, line_margin or line_margin_pct — these fields
  // do not exist in the portal schema, so they cannot leak.
}

export interface RiskComponent {
  name: "WEIGHTED_DISCOUNT_OVERAGE" | "VIOLATION_BREADTH"
      | "MARGIN_SHORTFALL" | "DISCOUNT_DEPTH";
  raw_value: Percent; weight: Percent; points: Percent; cap: Percent;
  explanation: string;                        // display verbatim
}

export interface ApprovalInboxItem {
  approval_request_id: string; approval_step_id: string;
  quote_id: string; quote_version_id: string;
  quote_number: string; version_number: number;
  title: string; customer_name: string;
  level: ApprovalLevel; sequence: number; reason: string;
  blended_risk_score: Percent; total_revenue: Money; margin_pct: Percent;
  requested_by_email: string;
  is_reapproval: boolean;                     // badge this prominently
  waiting_since: string;
}

export interface AttentionItem {
  id: string; source_type: string; source_id: string;
  type: string; severity: Severity;
  title: string; reason: string; impact: string;
  owner_role: Role; owner_user_id: string | null;
  recommended_action: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
  deal_id: string | null; quote_id: string | null;
  detail: Record<string, unknown>;
  created_at: string; resolved_at: string | null;
  acknowledged_at: string | null; acknowledged_by_user_id: string | null;
  nudge_count: number; last_nudged_at: string | null;
  escalated_at: string | null; escalation_note: string | null;
}

export interface DealHealthSignal {
  code: string; label: string; severity: Severity;
  detail: string; points: number;             // negative deduction
}

export interface SimulationResult {
  quote_version_id: string; simulated_at: string;
  baseline: SimulationScenario; proposed: SimulationScenario;
  margin_delta: Money; margin_pct_delta: Percent;
  revenue_delta: Money; risk_delta: Percent;
  approvals_added: string[]; approvals_removed: string[];
  verdict: string;                            // display verbatim
  persisted: false;
}
```

---

## 9. Screen-by-screen integration map

Mapped to the PDF's module letters.

| Screen | Endpoints | Notes |
|---|---|---|
| **A1** Login / signup | `POST /auth/login`, `/auth/signup` | Handle 429 |
| **A2** Product config | `GET/POST/PATCH /admin/products`, `/admin/product-variants`, `/admin/price-lists` | `is_promoted` toggle lives here |
| **A3** Discount tiers and chains | `GET/POST/PATCH /admin/policies`, `GET/PATCH /admin/settings` | Settings holds the escalation threshold and risk weights |
| **A4** Warehouses | `POST /admin/warehouses`, `GET/PATCH /admin/warehouses/{id}`, `POST /admin/inventory[/adjust]`, `GET /inventory` | `priority` and shipping cost drive the split |
| **A5** Subscription plans | `POST/PATCH /admin/products` with `billing_type=RECURRING` | Proration rules live in `/admin/settings` |
| **A6** Upsell rules | `PATCH /admin/products` (`is_promoted`), `/admin/settings` (`recommendation_min_margin_pct`) | |
| **A7** Reporting | `GET /reports/*`, `GET /reports/{name}/export` | Blob download for export |
| **B1** Top menu | `GET /users/me` | Route on `is_internal` |
| **B2** Quotations + pipeline | `GET /quotes`, `GET /deals?stage=` | One request per view |
| **B3** Quote builder | `GET /products`, `POST/PATCH/DELETE .../lines`, `PATCH .../discount`, `POST .../calculate` | Refresh from `calculate` after every change |
| **B4** Approval screen | `GET /approvals/inbox`, `GET /approvals/{id}`, `POST .../approve|reject|request-revision` | Show `financials` and `risk_components` |
| **B5** Upsell panel | `GET /quotes/{id}/recommendations`, `POST .../dismiss` | `is_promoted` → tag; add via `POST .../lines` then `calculate` |
| **B6** Warehouse split | `POST /orders/{id}/allocate`, `GET .../allocations` | Render `explanation` per line |
| **B7** Subscription + billing | `GET /billing/schedules`, `/summary`, `POST /billing/subscriptions/{id}/change|cancel`, `/billing/credit-notes` | |
| **B8** Portal | `GET /portal/quotes[/{id}]`, `GET/POST .../messages`, `POST .../confirm` | Separate shell; `Idempotency-Key` on confirm |
| **B9** Deal health | `GET /dashboard/control-tower`, `/attention-items`, `/deal-health`, `/reports/discount-anomalies` | Action buttons: resolve, acknowledge, nudge, escalate |
| Audit trail | `GET /audit/quotes/{id}/timeline` | Order by `sequence` |
| What-if | `POST /quote-versions/{id}/simulate` | Debounce; nothing persists |

---

## 10. Real-time features

**There are none.** Verified absent: no WebSocket endpoint, no SSE, no
`text/event-stream`, no long-poll. See
[`BACKEND_API_DOCUMENTATION.md`](./BACKEND_API_DOCUMENTATION.md) §19.

"Real time" in the PDF means recomputed-on-read, which the request/response
cycle satisfies. Use:

| Pattern | Where |
|---|---|
| **Refetch after mutation** | Primary. Every mutation returns the updated resource; use it directly |
| **Refetch on window focus** | Approval inbox, Control Tower — catches another user's action |
| **Interval polling** | Only the approval inbox and Control Tower, 30–60s, and only while the tab is visible |
| **Manual refresh** | PDF B1's "Reload Data" button — invalidate the catalog, stock and approval queries |

Do not poll a quote the user is editing: every read is authoritative, so
polling would fight the user's own edits.

If a future version needs push, the in-process event bus in
[`app/events.py`](../app/events.py) already emits 37 event types at the right
seams — an SSE endpoint subscribing to it would be a small addition. That is
noted as future work, not a current capability.

---

## 11. Pitfalls specific to this API

Ordered by how likely they are to cost an hour.

1. **`parseFloat` on money.** Silently wrong, and only visible when a customer disputes an invoice.
2. **Recomputing totals client-side.** They will disagree with the server. Always render what `calculate` returns.
3. **Assuming lists are arrays.** Paginated routes return `{items, total, limit, offset}`; reference collections return a bare array. §1.4 of the API doc lists which is which.
4. **`audit_events.limit` capped at 200.** The shared pagination bound applies; the old 1000 ceiling is gone.
5. **Reading `error.detail`.** There is no such field. It is always `error.code` / `error.message` / `error.details`.
6. **Treating cross-tenant 404 as a bug.** Deliberate, so ids cannot be enumerated. Do not "helpfully" show a permission message.
7. **Treating `ALREADY_CONFIRMED` as failure.** It means it already worked.
8. **Regenerating `Idempotency-Key` on retry.** Defeats the protection.
9. **Editing a non-`DRAFT` version.** Gate on `is_editable`, and offer "Create revision" on 409.
10. **Trusting the JWT's `role` claim.** Observability only. The server re-reads the user row every request, so a stale claim can disagree.
11. **Sending `unit_cost` on a line.** Rejected — `extra="forbid"`. Cost is server-side only.
12. **Expecting order-level and line-level discounts to add.** They compound: `100 × (1 − (1−line/100) × (1−order/100))`.
13. **Building an "OVERDUE invoice" filter.** Invoices never carry that status; use the computed `is_overdue` / `days_overdue` fields.
14. **`res.json()` on a report export.** It is binary; use `res.blob()`.
15. **Sending `""` for an unset filter.** Omit the parameter; typed query params reject empty strings.
16. **Omitting the body on `POST /submit` or `/send`.** Send `{}`.
17. **Designing for notifications.** `nudge` records and audits an intent; nothing is delivered. Show it as in-app state.

---

## 12. Local setup

```bash
# Backend
docker compose up -d                      # PostgreSQL on 5433
alembic upgrade head
python -m scripts.seed                    # deterministic demo data
uvicorn app.main:app --reload --port 8000

# Types
npx openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api/types.ts
```

Point the frontend at `VITE_API_URL=http://127.0.0.1:8000`, and add your dev
origin to the backend's `CORS_ORIGINS` (default already includes
`http://localhost:5173` and `http://localhost:3000` in `.env.example`).

### Demo credentials

All seeded users share the password `Password123!` — demo only.

| Email | Role | Use for |
|---|---|---|
| `sales@techsupply.com` | SALES | Quote building, the main workspace |
| `manager@techsupply.com` | MANAGER | First approval step |
| `finance@techsupply.com` | FINANCE | Second approval, billing |
| `ops@techsupply.com` | OPS | Allocation and fulfillment |
| `admin@techsupply.com` | ADMIN | Configuration area |
| `customer@acme.com` | CUSTOMER | The portal |

Seeded data: TechSupply Solutions (seller) and Acme Corporation (buyer, GOLD,
NET 30, 500,000 credit limit); 4 products; 2 warehouses (Main 60 laptops / 150
monitors, East 40 / 50); 7 policies; 1 sales team.

The canonical demo quote — 100 laptops @18%, 100 monitors @16%, 1 installation
@18%, 1 annual support @0% — produces net 132,710.00, cost 100,200.00, margin
32,510.00 (24.4970%), blended risk 32.44 MEDIUM, routing SALES_MANAGER →
FINANCE. Use those numbers as a fixture: if your UI shows anything else, the
client is transforming values it should be rendering.
