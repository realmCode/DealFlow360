# FRONTEND_CURRENT_STATE

## Finding: there is no frontend in this repository.

The rebuild directive assumed an existing frontend that should not be trusted.
The audit found something simpler and more consequential: **there is nothing to
distrust.** This is a backend-only repository.

### Evidence

```
DealFlow360/
├── app/            FastAPI application (103 paths, 117 operations)
├── alembic/        migrations (head 7b431beeb960)
├── docs/           17 markdown documents + openapi.json + api_examples.json
├── scripts/        seed, verify_db, self_audit, capture_api_examples
├── tests/          24 modules, 434 tests
├── SKILLS_ALL/     UI/UX skill library (not application code)
├── .venv/          Python 3.11
├── image.png       Excalidraw wireframe, 18 screens (the IA reference)
├── requirements.txt, pytest.ini, alembic.ini, docker-compose.yml
├── README.md, PROGRESS.md, Start.md (empty)
```

| Probe | Result |
|---|---|
| Directory named `frontend/`, `client/`, `web/`, `ui/` | none |
| `package.json` anywhere outside `SKILLS_ALL/` and `.venv/` | none |
| Lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`) | none |
| `.tsx` / `.jsx` / `.vue` / `.svelte` application source | none |
| `index.html` entry point | none |
| Any HTTP client, router, or state-management dependency | none |
| Git history (13 commits) | every commit is backend or docs |

`Start.md` is a zero-byte file.

### What this changes

There is no legacy code to migrate, no design debt to unpick, and no wrong
assumptions baked into an existing client. Sections of the directive written
for a rewrite — "do not trust the old frontend", "what the current frontend
gets wrong" — have no subject.

The corresponding risk is different: with no existing client, **every**
contract detail has to come from the backend rather than from a working
example. That is why Phase 0 executed the canonical flow against the live API
and captured real response shapes rather than reading documentation alone.

### What already exists and is worth using

The backend ships an unusually complete integration surface. These are inputs
to the build, not code to replace:

| Asset | Size | Use |
|---|---|---|
| `docs/openapi.json` | 478 KB | verified identical to the live spec; the type-generation source |
| `docs/api_examples.json` | 246 KB | recorded real request/response pairs |
| `docs/FRONTEND_INTEGRATION_GUIDE.md` | 36 KB | money handling, idempotency, pagination, error branching |
| `docs/ROLE_PERMISSION_MATRIX.md` | 18 KB | per-endpoint RBAC |
| `docs/ENTITY_STATE_LIFECYCLES.md` | 28 KB | state machines |
| `docs/USER_JOURNEYS.md` | 34 KB | flow-level narrative |
| `docs/BACKEND_API_DOCUMENTATION.md` | 74 KB | full error-code catalogue |

The backend is already configured to expect a browser client:
`CORS_ORIGINS=http://localhost:5173,http://localhost:3000` and
`allow_headers` includes `Idempotency-Key`. Port 5173 is the Vite default, so
the intended client is a Vite dev server.

### Consequence for the plan

"Rebuild the frontend" is a greenfield build. Sections 1–7 of the directive
(backend audit, verification, fixing) were therefore executed in full and are
recorded in `BACKEND_CAPABILITY_MATRIX.md`; sections about auditing existing
frontend code are answered by this document.
