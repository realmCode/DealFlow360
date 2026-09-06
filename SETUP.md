# DealFlow360 — deployment and demo data

**The demo data is not stored in the repository as fixtures.** There is no
`data.sql`, no JSON dump and no committed database. It is generated
deterministically by `scripts/seed.py` directly into PostgreSQL, which is why a
fresh clone looks empty until you run the seed.

That is deliberate: the seed goes through the real services, so the demo tenant
obeys the same constraints, validation and audit rules as production data. It is
also **idempotent** — running it twice creates nothing the second time.

---

## Prerequisites

| | |
|---|---|
| Python | 3.11 or newer |
| Node | 20 or newer |
| Docker | for PostgreSQL 16 (or bring your own Postgres) |

---

## From clone to running

```bash
git clone https://github.com/realmCode/DealFlow360.git
cd DealFlow360
```

### 1. Database

```bash
docker compose up -d          # PostgreSQL 16 on :5433
```

Uses port 5433 so it will not clash with a local Postgres on 5432.

### 2. Backend configuration

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # paste into JWT_SECRET_KEY
```

`.env` is gitignored, so it will never arrive with the clone — this step is
mandatory. The app refuses to start in staging or production with the
placeholder secret.

Check `CORS_ORIGINS` includes wherever the UI will run. It defaults to
`http://localhost:5173,http://localhost:3000`.

### 3. Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # creates all 38 tables
```

### 4. **Load the demo data** ← the step that is being missed

```bash
python -m scripts.seed
```

Expected output on a fresh database:

```
roles 6 · organizations 2 · users 6 · customer_profiles 1 · contacts 1
products 4 · warehouses 2 · inventory 4 · policies 7 · sales_teams 1
```

Run it again and every count is `0` — that is the idempotency working, not a
failure.

There is also an API route if the server is already up:

```bash
curl -X POST http://127.0.0.1:8010/admin/seed \
     -H "Authorization: Bearer <an ADMIN token>"
```

### 5. Run it

```bash
uvicorn app.main:app --port 8010                 # API + /docs

cd frontend
cp .env.example .env.local                       # optional; defaults are fine
npm install
PORT=3000 npm run dev                            # UI on :3000
```

**The port matters.** The backend whitelists `http://localhost:5173` and
`http://localhost:3000` exactly. Serving the UI from any other origin will fail
CORS. Use `localhost`, not `127.0.0.1` — origins are matched literally.

### 6. Before a live demo (optional but recommended)

```bash
python -m scripts.demo_reset
```

Restores stock to 60 Main / 40 East and creates a fresh DRAFT quotation on the
canonical configuration, then prints the URL to open. Repeated demo runs
legitimately consume inventory, and an exhausted warehouse makes the allocator
backorder everything — correct behaviour, but it hides the multi-warehouse
split. See `DEMO_SCRIPT.md`.

---

## What the seed actually creates

### Organizations

| Name | Kind |
|---|---|
| TechSupply Solutions | SELLER — the tenant you operate |
| Acme Corporation | CUSTOMER — the buyer, GOLD tier, NET_30, 500,000 credit limit |

### Users — password `Password123!` for all six

| Email | Name | Role |
|---|---|---|
| sales@techsupply.com | Sam Rivera | SALES |
| manager@techsupply.com | Morgan Chen | MANAGER |
| finance@techsupply.com | Fran Delgado | FINANCE |
| ops@techsupply.com | Omar Petrov | OPS |
| admin@techsupply.com | Avery Stone | ADMIN |
| customer@acme.com | Casey Nolan | CUSTOMER |

The password comes from `SEED_DEFAULT_PASSWORD` in `.env`. Change it there
before any non-demo deployment.

### Products

| SKU | Name | Category | List | Cost | Billing |
|---|---|---|---:|---:|---|
| HW-LAPTOP-01 | Business Laptop | HARDWARE | 1,200.00 | 800.00 | one-time |
| HW-MONITOR-27 | 27" Monitor | HARDWARE | 400.00 | 200.00 | one-time |
| SV-INSTALL-01 | Installation Service | SERVICE | 500.00 | 150.00 | one-time |
| SB-SUPPORT-01 | Annual Support Plan | SUBSCRIPTION | 300.00 | 50.00 | recurring, yearly |

### Warehouses and stock

| Code | Name | Priority | Shipping | Laptops | Monitors |
|---|---|---:|---:|---:|---:|
| MAIN | Main Warehouse (San Jose) | 10 | 120.00 | 60 | 150 |
| EAST | East Depot (Newark) | 20 | 180.00 | 40 | 50 |

Priority is what produces the canonical **60/40 split** on a 100-laptop order.

### Governance policies (7)

| Code | Type | Scope | Rule | Breach routes to |
|---|---|---|---|---|
| GOLD-HW-CEILING | Category ceiling | Gold · Hardware | ≤ 15% | Sales Manager |
| GOLD-SV-CEILING | Category ceiling | Gold · Service | ≤ 10% | Sales Manager |
| GOLD-SB-CEILING | Category ceiling | Gold · Subscription | ≤ 10% | Sales Manager |
| STD-HW-CEILING | Category ceiling | Any tier · Hardware | ≤ 10% | Sales Manager |
| MIN-MARGIN-10 | Minimum margin | All | ≥ 10% | Finance |
| DISCOUNT-AUTHORITY-20K | Signing authority | All | ≤ 20,000 | Finance |
| GOLD-TERMS-60 | Payment terms | Gold | ≤ 60 days | Finance |

These are the rules that make the demo work. Every discount breach, risk score
and approval route in the product derives from this table — nothing is hardcoded
in the application.

Plus one sales team (WEST) so the Sales Team filter on reports has something to
filter by.

### What the seed does **not** create

No quotations, deals, orders, invoices or approvals. Those are created by using
the product — which is the point. `scripts/demo_reset.py` creates one DRAFT
quotation if you want a running start.

---

## Verify it worked

```bash
python -m scripts.verify_db      # 38 tables, FKs, constraints, no float money
ENVIRONMENT=test pytest          # 434 tests, needs the mydb_test database
```

Then sign in at `http://localhost:3000/login` and press **Demo accounts** — all
six roles should be listed. If that dialog is empty or login fails, the seed did
not run.

Quick API check:

```bash
curl -s -X POST http://127.0.0.1:8010/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"sales@techsupply.com","password":"Password123!"}' | head -c 120
```

A token means the data is there.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Login fails for every account | Seed never ran | `python -m scripts.seed` |
| "Demo accounts" dialog errors | API unreachable or unseeded | Check `:8010/health`, then seed |
| CORS errors in the browser | UI served from an unlisted origin | Use `localhost:3000` or `localhost:5173`, or add yours to `CORS_ORIGINS` |
| App refuses to start | `JWT_SECRET_KEY` still the placeholder | Generate one into `.env` |
| `alembic upgrade head` fails | Postgres not up, or wrong `DATABASE_URL` | `docker compose up -d`; URL must be `postgresql+asyncpg://` |
| Allocation backorders everything | Stock consumed by earlier runs | `python -m scripts.demo_reset` |
| Tests hang or fail | `mydb_test` missing | `docker compose up -d` provisions it; run with `ENVIRONMENT=test` |

---

## Deploying somewhere real

The seed is a **demo fixture**. Before exposing this to anyone:

1. Set a real `JWT_SECRET_KEY` and change `SEED_DEFAULT_PASSWORD`.
2. Do not run `scripts/seed.py` against a real tenant — it creates six users
   with a published password.
3. Set `VITE_DEMO_MODE=false` in the frontend so the demo picker and the role
   switcher are compiled out.
4. Set `ENVIRONMENT=production`, which closes `/docs` and rejects a wildcard
   `CORS_ORIGINS`.
5. The auth rate limiter keeps state in-process — behind multiple workers each
   process holds its own counters. Shared state would be needed for a real
   multi-worker deployment. This is a known limitation, documented rather than
   hidden.
