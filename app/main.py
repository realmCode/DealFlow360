"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import dispose_engine
from app.errors import DealFlowError
from app.events import registered_handlers
from app.routers import ALL_ROUTERS

DESCRIPTION = """
**DealFlow360** — an intelligent, self-governing sales operations platform.

The backend is the source of truth. It calculates and persists every
authoritative value; the client renders them.

* Totals, discounts, tax, cost, margin and margin % — `CommercialEngine`
* Discount ceilings, margin floors and blended risk — `PolicyEngine`
* Material-change detection and approval staleness — `DecisionFabric`
* Approval routing, ordered steps and decisions — `ApprovalService`
* Atomic multi-warehouse allocation — `InventoryService`
* One-time + recurring billing schedules — `BillingService`

No client can approve a quote, edit an approved version, see another
organization's data, or make a customer see cost or margin.

### Authentication
`POST /auth/login` then send `Authorization: Bearer <access_token>`.

### Roles
`SALES` `MANAGER` `FINANCE` `OPS` `CUSTOMER` `ADMIN`

### Errors
Every non-2xx response uses one envelope:

```json
{"error": {"code": "STALE_APPROVAL", "message": "...", "details": {}}}
```

### Idempotency
Send an `Idempotency-Key` header on `POST /portal/quotes/{id}/confirm` and
`POST /orders/{id}/allocate`. A retry with the same key returns the original
result instead of duplicating the effect.
"""

_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_FAILED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Importing the models package registers all 33 tables; importing the
    # services registers the audit-trail event subscriber.
    import app.models  # noqa: F401
    import app.services.audit_service  # noqa: F401

    yield
    await dispose_engine()


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Idempotency-Key"],
    )

    # ---------------------------------------------------- error handling
    @app.exception_handler(DealFlowError)
    async def _dealflow_error(
        request: Request, exc: DealFlowError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            content = detail
        else:
            content = _envelope(
                _STATUS_CODES.get(exc.status_code, "HTTP_ERROR"), str(detail)
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(content),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder(
                _envelope(
                    "VALIDATION_ERROR",
                    "Request payload failed validation.",
                    {"errors": exc.errors()},
                )
            ),
        )

    # -------------------------------------------------------- observability
    @app.get("/health", tags=["system"], summary="Liveness and dependency check")
    async def health() -> dict[str, Any]:
        import sqlalchemy as sa

        from app.db import get_engine

        database = "up"
        try:
            async with get_engine().connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - surfaced to the operator
            database = f"down: {type(exc).__name__}"

        return {
            "status": "ok" if database == "up" else "degraded",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "database": database,
            "event_handlers": registered_handlers(),
        }

    @app.get("/", tags=["system"], include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/health",
        }

    for router in ALL_ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)

    return app


app = create_app()
