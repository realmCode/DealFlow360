# SECURITY AUDIT

Audited against the running instance at `http://127.0.0.1:8000` and the source
in [`app/`](../app/). Findings marked **VERIFIED** were reproduced against the
live server; **CODE** findings are read from source.

Severity scale is calibrated to *this* product — a B2B sales platform holding
commercial terms, cost and margin data — not to a generic checklist. Findings
that matter only for a public-internet production deployment are marked as such,
because the PDF asks for a hackathon deliverable, not a hardened SaaS.

---

## Summary

| Severity | Count | Fix before frontend? |
|---|---|---|
| **Critical** | 1 | **Yes** |
| **High** | 2 | **Yes** |
| **Medium** | 4 | 2 yes, 2 deferrable |
| **Low** | 5 | No |
| **Informational** | 4 | No |

**Overall posture: strong on the things that are hard, weak on two things that
are trivial to fix.** Authorization, tenant isolation, IDOR resistance, race
conditions, input validation and audit logging are all genuinely well built and
tested. The critical and high findings are configuration hygiene, each fixable in
minutes.

---

## Critical

### SEC-1 · The JWT signing key is a committed source-code default — **VERIFIED**

| Field | Value |
|---|---|
| Severity | **Critical** (development-config origin, but total auth bypass) |
| Component | [`app/config.py`](../app/config.py) `jwt_secret_key` |
| Fix before frontend? | **Yes** |

**Finding.** The running instance is signing tokens with the placeholder default
declared in `app/config.py`. Verified against the live process:

```
using_default_jwt_secret: True
```

Compounding it, **no `.env` or `.env.example` file exists in the repository**,
despite README §4 instructing `cp .env.example .env`. There is therefore no
mechanism by which a developer would be prompted to override the key, and the
app silently runs on every hardcoded default.

**Impact.** The signing key is readable by anyone with repository access. Because
`create_access_token` embeds `sub`, `org` and `role`, a forged token can claim
any user id, any organization and the `ADMIN` role. That defeats authentication,
authorization and tenant isolation simultaneously — every other control in this
document sits downstream of it.

Mitigating context: `get_current_user` re-reads the user row on every request,
so a forged `sub` must correspond to a real, active user in an active
organization. That reduces "invent a user" to "impersonate a known user", which
is still complete compromise.

**Recommended fix.**
1. Add `.env.example` with every variable documented and an obviously-invalid placeholder.
2. Make `Settings` reject the placeholder when `environment != "development"` — a `model_validator` that raises if `jwt_secret_key` starts with `change-me` and the environment is staging or production.
3. Generate a real key for any shared demo: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
4. Confirm `.env` is git-ignored. Current `.gitignore` contains only `__pycache__` and `SKILLS_ALL`, so **`.env` would currently be committed if created.** Fix this first.

---

## High

### SEC-2 · CORS echoes any origin with credentials enabled — **VERIFIED**

| Field | Value |
|---|---|
| Severity | **High** |
| Component | [`app/main.py`](../app/main.py) `CORSMiddleware` |
| Fix before frontend? | **Yes** — and the frontend needs a real origin list anyway |

**Finding.** Configuration is `allow_origins=["*"]` with
`allow_credentials=True`. I expected the browser to reject that combination, but
Starlette's behaviour is worse than that. Verified live:

Preflight with a hostile origin:

```
> OPTIONS /auth/login
> Origin: http://evil.example.com
< HTTP/1.1 200 OK
< access-control-allow-origin: http://evil.example.com
< access-control-allow-credentials: true
< access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
< vary: Origin
```

Starlette **echoes the requesting origin** on preflight rather than returning
`*`, so the browser's wildcard-plus-credentials protection never engages. Any
website passes preflight with credentials permitted, for every method.

Simple request:

```
> GET /health
> Origin: http://evil.example.com
< access-control-allow-origin: *
< access-control-allow-credentials: true
```

**Impact today: limited.** Authentication is a `Authorization: Bearer` header,
not a cookie. A hostile page cannot read the victim's token from another origin's
`localStorage`, and there is no ambient credential for the browser to attach. So
this is not currently exploitable for data theft.

**Impact if anything changes: severe.** The moment the frontend stores the token
in a cookie — a common and otherwise reasonable choice — this configuration
becomes a full cross-origin read primitive against every endpoint. It is also
simply wrong: the server currently advertises that it trusts every origin on the
internet.

**Recommended fix.** Set an explicit origin list and stop advertising credential
support that Bearer auth does not need:

```
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

and set `allow_credentials=False` unless cookie auth is deliberately adopted.
Also narrow `allow_methods` and `allow_headers` from `["*"]` to the methods and
headers actually used, so the preflight response stops describing a larger attack
surface than exists.

---

### SEC-3 · No rate limiting on authentication — **CODE**

| Field | Value |
|---|---|
| Severity | **High** for any shared deployment; Medium for a local demo |
| Component | [`app/routers/auth.py`](../app/routers/auth.py) |
| Fix before frontend? | **Yes** — cheap, and it is a predictable judge question |

**Finding.** `POST /auth/login`, `/auth/signup` and `/auth/refresh` have no rate
limiting, no lockout, no CAPTCHA and no failed-attempt tracking. README §24 item
9 acknowledges this honestly.

**Impact.** Unlimited credential stuffing. The demo password is
`Password123!` across six seeded accounts, which is exactly the kind of password
a dictionary attack finds immediately. bcrypt at 12 rounds throttles an attacker
to roughly single-digit guesses per second per core, which is meaningful
protection but not a substitute for a limiter — and it simultaneously makes
`/auth/login` a cheap CPU-exhaustion target.

**Recommended fix.** A per-IP and per-email sliding-window limiter on the three
auth routes (for example 10 attempts per 15 minutes), returning **429** with the
standard error envelope and a `Retry-After` header. Since the error envelope
already has a `code` field, use `RATE_LIMITED` so the frontend can render a
specific message. In-process counters are adequate for a single-worker demo and
should be documented as needing shared state behind multiple workers.

This is also the only way the frontend can implement the 429 handling that
[`FRONTEND_INTEGRATION_GUIDE.md`](./FRONTEND_INTEGRATION_GUIDE.md) will describe
— currently 429 is unreachable, so that error path is untestable.

---

## Medium

### SEC-4 · Refresh tokens are stateless with no revocation — **CODE**

| Field | Value |
|---|---|
| Severity | Medium |
| Component | [`app/middleware/auth.py`](../app/middleware/auth.py) |
| Fix before frontend? | No — document it |

**Finding.** Refresh tokens are self-contained JWTs with a 7-day lifetime and no
server-side store. There is no revocation list and no rotation-family tracking,
so a stolen refresh token stays valid until expiry. `POST /auth/refresh` issues a
new pair but does not invalidate the presented token, so a leaked refresh token
can be replayed repeatedly and in parallel with the legitimate user.

**Partial mitigation that genuinely helps.** `IdentityService.refresh` re-reads
the user row and rejects inactive users, so deactivating an account immediately
kills refresh. That is a real control and better than many implementations.

**Recommended fix (post-hackathon).** Persist a `refresh_tokens` table keyed by
`jti` with `revoked_at`, rotate on every refresh, and revoke the whole family on
reuse detection. Out of scope for the deliverable; belongs in the "what we would
build next" note that PDF §8 asks for.

---

### SEC-5 · `ADMIN` can decide any approval step — **CODE**

| Field | Value |
|---|---|
| Severity | Medium |
| Component | [`app/services/approval_service.py`](../app/services/approval_service.py) |
| Fix before frontend? | No — intentional, audited, documented |

**Finding.** The per-step role check is bypassed for `ADMIN`, so an
administrator can satisfy a `FINANCE` step regardless of the configured chain.
README §24 item 10 acknowledges this.

**Why it is not High.** The self-approval prohibition still applies to `ADMIN` —
they cannot decide a quote they authored or submitted. Every decision writes an
`approval_decisions` row with actor identity, role, email, reason and a
financial snapshot. So the capability is constrained and fully attributable
rather than silent.

**Impact.** It concentrates authority: the role that configures the discount
ceilings can also approve breaches of them. That is a separation-of-duties
weakness a thorough judge may well probe.

**Recommended fix.** Split configuration authority from emergency approval. Keep
`ADMIN` for configuration and introduce a narrowly-scoped break-glass capability
that is explicitly flagged in the audit trail as an override rather than a normal
decision. Low effort, good story; deferrable past the frontend.

---

### SEC-6 · Attention-item ownership is recorded but not enforced — **CODE**

| Field | Value |
|---|---|
| Severity | Medium |
| Component | [`app/routers/dashboard.py`](../app/routers/dashboard.py) |
| Fix before frontend? | **Yes** — trivial and prevents a demo embarrassment |

**Finding.** `POST /dashboard/attention-items/{item_id}/resolve` is guarded by
`InternalUser` only. Any employee role can resolve any item, including a
`CRITICAL` `STALE_APPROVAL` item whose `owner_role` is `FINANCE`.

**Impact.** A `SALES` user can clear the governance alert raised because their
own quote went stale. The underlying block still holds — `assert_confirmable`
independently re-checks staleness, so resolving the alert does **not** unblock
the order — but the Control Tower, which the PDF positions as the manager's
early-warning system, can be silently emptied by the person it is warning about.

**Recommended fix.** Restrict resolution to the item's `owner_role`, the
assigned `owner_user_id`, or `ADMIN`. Return 403 with `owner_role` in `details`
so the UI can explain why the button is disabled.

---

### SEC-7 · `debug=True` and permissive defaults ship as the default posture — **VERIFIED**

| Field | Value |
|---|---|
| Severity | Medium |
| Component | [`app/config.py`](../app/config.py) |
| Fix before frontend? | Partially — bundle with SEC-1 |

**Finding.** Verified live: `debug: True`, `environment: development`,
`cors_allows_all: True`. All three are the shipped defaults with no `.env` to
override them. `/docs`, `/redoc` and `/openapi.json` are unauthenticated in
every environment.

**Impact.** Open API documentation is correct and desirable for a hackathon — it
is how a judge explores the system, and PDF §8 effectively expects it. The
concern is only that there is no environment gate, so a production deployment
would inherit the demo posture by default.

**Recommended fix.** Keep the docs open for the demo. Add a validator that
refuses to start with `debug=True` or `cors_origins="*"` when
`environment in {"staging", "production"}`, and gate `docs_url`/`redoc_url` on
the same condition. This is a five-line change that turns an accident into a
deliberate decision.

---

## Low

### SEC-8 · Inline authorization is invisible to the API contract — **CODE**

`OpsUser` is defined in [`app/dependencies.py`](../app/dependencies.py) and never
used. Instead `orders.py` and `billing.py` check roles inside handler bodies.
The enforcement is correct, but it does not appear in the OpenAPI schema, so
generated clients and `/docs` under-describe the real restrictions, and a future
refactor could drop a check without any contract test failing. Fix by converting
to declared dependencies (tracked as P1-10 in
[`BACKEND_GAP_ANALYSIS.md`](./BACKEND_GAP_ANALYSIS.md)).

### SEC-9 · No per-record ownership scoping on deals and quotes — **CODE**

Any internal user in an organization can read any deal, and any `SalesUser` can
modify any deal, not only ones they own. Correct for a small co-located sales
team and arguably correct for the PDF's manager-oversight requirement, but it
would need territory scoping at real scale. Not a defect for this deliverable.

### SEC-10 · Deal stage transitions are unguarded — **CODE**

`PATCH /deals/{deal_id}` accepts any `DealStage`, so a `CLOSED_WON` deal can be
moved back to `QUALIFICATION`, decoupling it from the confirmed order that set
it. Data-integrity rather than security. Tracked as P1-9.

### SEC-11 · Idempotency keys are never pruned — **CODE**

`expires_at` is written and nothing deletes expired rows. Unbounded table growth;
a slow resource issue, not an access-control one. Tracked as P3-1.

### SEC-12 · Password policy is minimal — **CODE**

`SignupRequest` requires 8–72 bytes and rejects all-alphabetic or all-numeric
passwords. No complexity, no breach-list check, no reuse prevention. Adequate
for the deliverable; `Password123!` passes, which is the point for a demo.

---

## Informational — controls that are genuinely well built

These are recorded because a security section listing only problems would
misrepresent the system.

### SEC-I1 · IDOR resistance is correct, and correctly designed — **VERIFIED**

Cross-tenant access returns **404, not 403**, so response codes cannot be used
to enumerate identifiers in other organizations. Verified:

```json
{"error":{"code":"NOT_FOUND","message":"Deal not found.","details":{}}}
```

Two distinct isolation mechanisms are used deliberately. Internal users match on
`organization_id` via `scope_to_org`. Customer portal users never match on
`organization_id` at all — access is granted through
`customer_profiles.customer_organization_id`, checked explicitly in
`NegotiationService.authorize`, which returns 404 with
`details.reason = "not issued to your organization"`.

`tests/test_tenant_isolation.py` covers this with 20 tests across two tenants.

### SEC-I2 · Privilege separation is bidirectional — **VERIFIED**

Most systems block customers from internal endpoints and stop there. This one
also blocks employees from portal endpoints:

```json
{"error":{"code":"INTERNAL_USER_FORBIDDEN","message":"Only customer portal users may use the portal endpoints.","details":{"your_role":"SALES"}}}
```

That second direction is what makes PDF §7's "real, separate, restricted view"
constraint true rather than nominal — without it, the redacted view would be an
alias for the internal one.

Redaction itself is **structural**: `QuotePublicRead`,
`QuoteVersionPublicRead`, `QuoteLinePublicRead` and `OrderPublicRead` do not
declare cost, margin or risk fields at all. A developer cannot forget to redact a
field that does not exist in the schema. The end-to-end test asserts the
serialised portal payload contains none of `unit_cost`, `line_cost`, `margin`,
`internal_cost`, `risk`, nor the literal internal values.

### SEC-I3 · Race conditions and duplicate submission are properly handled — **CODE + tests**

- Allocation takes `SELECT ... FOR UPDATE` over every stock row for the product **before** deciding anything, locking in `inventory.id` order with lines processed in `product_id` order, giving every transaction identical lock ordering and eliminating the deadlock window.
- `CHECK (quantity_reserved <= quantity_on_hand)` is the database backstop, so even a service bug cannot over-allocate.
- Confirmation is protected twice: `IdempotencyService` with a SHA-256 body fingerprint under `SELECT FOR UPDATE`, and `UNIQUE (sales_orders.quote_version_id)` above it. Even with no `Idempotency-Key`, a duplicate order is impossible.
- A reused key with a different body returns 409 `IDEMPOTENCY_KEY_REUSED` rather than silently replaying the wrong response — the correct and less obvious choice.
- Approval decisions serialise on `current_step_sequence`; the loser of a simultaneous decision gets 409 `NO_PENDING_STEP` listing what was already decided.
- Partial unique index `WHERE status = 'PENDING'` guarantees at most one open approval per version.

Covered by `pytest -m concurrency`.

### SEC-I4 · Input validation, error hygiene and audit logging — **VERIFIED**

- Every request model sets `extra="forbid"`, so unexpected fields are rejected rather than ignored. This is what prevents a client supplying `unit_cost` — cost is copied server-side from the catalog and is structurally unspendable as client input.
- Path and query parameters are typed; a malformed UUID yields 422 before any handler runs.
- All database access is through SQLAlchemy with parameter binding; no string-interpolated SQL exists.
- Money is `Decimal`/`NUMERIC` end to end with zero float columns (asserted by both a test and `scripts/verify_db.py`), so margin decisions cannot drift.
- Errors are a single envelope with a stable machine-readable `code`. Messages are written for users and leak no stack traces, SQL, or internal identifiers. Validation errors expose Pydantic's `loc`/`msg`/`type`, which is appropriate.
- `audit_events` is append-only — the table has **no `updated_at` column**, so there is structurally nothing to rewrite history with — with a monotonic `sequence` for stable total ordering, and money stored as strings so a JSONB float round-trip cannot corrupt the record of a decision.
- Passwords are bcrypt at 12 rounds, with an explicit rejection of inputs over 72 bytes rather than silently hashing a truncated prefix.
- Tokens are typed: presenting a refresh token as a bearer token yields 401 `WRONG_TOKEN_TYPE`.
- User state is re-read on every request, so deactivation and role changes take effect immediately rather than at token expiry.

---

## Fix-before-frontend checklist

| # | Finding | Effort | Rationale |
|---|---|---|---|
| 1 | **SEC-1** — add `.env.example`, add `.env` to `.gitignore`, generate a real `JWT_SECRET_KEY`, reject the placeholder outside development | Minutes | Everything else is downstream of the signing key |
| 2 | **SEC-2** — explicit `CORS_ORIGINS`, `allow_credentials=False`, narrowed methods and headers | Minutes | The frontend needs a real origin list regardless, and the current config trusts every origin |
| 3 | **SEC-3** — rate limit the three auth routes, return 429 with `RATE_LIMITED` | Small | Predictable judge probe; also makes the frontend's 429 path testable |
| 4 | **SEC-6** — enforce attention-item ownership on resolve | Small | Prevents a rep clearing the alert about their own stale quote |
| 5 | **SEC-7** — environment validator refusing debug and wildcard CORS in staging/production | Small | Bundles naturally with 1 and 2 |

Deferred with documented rationale: SEC-4 (refresh revocation), SEC-5
(break-glass role), SEC-8 to SEC-12.

---

## Deliberately not added

Per the instruction not to introduce security features for appearance:

| Control | Why not |
|---|---|
| CSRF tokens | Bearer-header auth is not ambient; there is no cookie to ride. Adding CSRF would imply a threat model this app does not have |
| Field-level encryption | No PII beyond name, email and phone. Commercial terms are the product, not a secret to hide from the tenant that owns them |
| WAF / IP allowlisting | Infrastructure concerns, not application concerns |
| 2FA | Not in the PDF; would add a login flow the demo has no time to show |
| Audit-log signing / hash chaining | `sequence` plus append-only storage plus no `updated_at` column is proportionate. Cryptographic chaining defends against a database-admin threat this deliverable does not model |
| Content Security Policy | Belongs with the frontend, not the API |
| Request signing | No third-party integrations exist to sign for |
