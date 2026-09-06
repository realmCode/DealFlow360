# Database export

A ready-to-restore PostgreSQL dump of the DealFlow360 demo tenant, so a server
can be brought up without installing Python, running Alembic or running the
seed script.

Generated from a **clean** database — migrated to head and seeded, with none of
the quotations, orders or approvals that accumulate from using or testing the
app. Restore it and you get a pristine demo tenant.

| File | Format | Size | Use |
|---|---|---:|---|
| `dealflow360_demo.dump` | custom (`-Fc`) | 204 KB | **Preferred.** Restore with `pg_restore`; compressed, parallelisable, selective |
| `dealflow360_demo.sql` | plain SQL | 145 KB | Restore with `psql`; readable, works anywhere, good for managed hosts that only accept SQL |
| `dealflow360_schema.sql` | plain SQL | 122 KB | Structure only, no rows — for an empty environment you intend to seed yourself |

Both full dumps were taken with `--no-owner --no-privileges`, so they restore
under whatever role you connect as. No `dealflow360`-specific database user is
required.

**PostgreSQL 16.** Restoring into an older major version is not supported.

---

## Restore

Create the database first — the dumps do not contain `CREATE DATABASE`.

### Custom format (recommended)

```bash
createdb -h <host> -U <user> dealflow360
pg_restore -h <host> -U <user> -d dealflow360 --no-owner --no-privileges \
           dealflow360_demo.dump
```

### Plain SQL

```bash
createdb -h <host> -U <user> dealflow360
psql -h <host> -U <user> -d dealflow360 --set ON_ERROR_STOP=on \
     -f dealflow360_demo.sql
```

### Into a Docker container

```bash
docker exec -i <container> psql -U postgres -c "CREATE DATABASE dealflow360;"
docker exec -i <container> pg_restore -U postgres -d dealflow360 \
        --no-owner --no-privileges < dealflow360_demo.dump
```

### Managed hosts (RDS, Cloud SQL, Neon, Supabase, Render)

Most accept the plain file over a normal connection:

```bash
psql "$DATABASE_URL" --set ON_ERROR_STOP=on -f dealflow360_demo.sql
```

If the provider refuses `SET` statements in the header, use the custom dump with
`pg_restore --no-owner --no-privileges --no-comments`.

---

## Point the app at it

```bash
# .env — note the +asyncpg driver, the app rejects anything else
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/dealflow360
```

Then start the API as usual. **Do not run `alembic upgrade head` afterwards** —
the dump already contains the schema and the `alembic_version` row
(`7b431beeb960`), so Alembic will correctly report there is nothing to do.

---

## What you get

| | |
|---|---|
| Tables | 39 (38 application + `alembic_version`) |
| Alembic revision | `7b431beeb960` (head) |
| Organizations | TechSupply Solutions (seller) · Acme Corporation (buyer, GOLD, NET_30, 500,000 credit) |
| Users | 6 — one per role |
| Products | 4 |
| Warehouses | 2 (MAIN priority 10, EAST priority 20) |
| Inventory | 4 rows — 60 + 40 laptops, 150 + 50 monitors |
| Policies | 7 governance rules |
| Sales teams | 1 |
| Quotes / orders / invoices | **none** — created by using the product |

### Sign-in accounts — password `Password123!`

| Email | Role |
|---|---|
| sales@techsupply.com | SALES |
| manager@techsupply.com | MANAGER |
| finance@techsupply.com | FINANCE |
| ops@techsupply.com | OPS |
| admin@techsupply.com | ADMIN |
| customer@acme.com | CUSTOMER |

> **Change these before anything public.** Six accounts with a published
> password is a demo fixture, not a deployment. See the production checklist at
> the end of `../SETUP.md`.

---

## Verify the restore

```bash
psql "$DATABASE_URL" -c "
select 'tables' k, count(*)::text v from information_schema.tables where table_schema='public'
union all select 'users', count(*)::text from users
union all select 'products', count(*)::text from products
union all select 'policies', count(*)::text from policies
union all select 'alembic', version_num from alembic_version;"
```

Expect `tables 39 · users 6 · products 4 · policies 7 · alembic 7b431beeb960`.

Then confirm the application accepts it:

```bash
curl -s -X POST http://<api-host>/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"sales@techsupply.com","password":"Password123!"}' | head -c 120
```

A token means you are done.

---

## Regenerating this export

```bash
docker exec dealflow360-postgres psql -U postgres \
  -c "DROP DATABASE IF EXISTS dealflow360_export;" \
  -c "CREATE DATABASE dealflow360_export;"

export DATABASE_URL="postgresql+asyncpg://postgres:mysecretpassword@localhost:5433/dealflow360_export"
python -m alembic upgrade head
python -m scripts.seed

docker exec dealflow360-postgres pg_dump -U postgres -d dealflow360_export \
  --no-owner --no-privileges -Fc > db/dealflow360_demo.dump
docker exec dealflow360-postgres pg_dump -U postgres -d dealflow360_export \
  --no-owner --no-privileges > db/dealflow360_demo.sql
docker exec dealflow360-postgres pg_dump -U postgres -d dealflow360_export \
  --no-owner --no-privileges --schema-only > db/dealflow360_schema.sql
```

### Why there is no data-only dump

`quote_versions`, `quote_lines` and `approval_requests` carry circular foreign
keys, so a `--data-only` file cannot be loaded without `--disable-triggers`,
which needs superuser. Shipping one would be a footgun. If you already have the
schema, run `python -m scripts.seed` instead — it is idempotent and goes through
the real services.

---

## Verified

This export was restored into two fresh databases (both `pg_restore` and `psql`
paths), the API was started against the result, and `sales@techsupply.com`
signed in and read products, policies and warehouses successfully.
