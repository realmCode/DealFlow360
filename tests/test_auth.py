"""Authentication: signup, login, JWT, refresh, protected routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import SEED_PASSWORD, login, signup


async def test_signup_creates_user_and_organization(client: AsyncClient) -> None:
    body = await signup(
        client,
        email="founder@newco.dev",
        full_name="Founder",
        role="ADMIN",
        organization_name="NewCo",
    )
    assert body["user"]["email"] == "founder@newco.dev"
    assert body["user"]["role"] == "ADMIN"
    assert body["user"]["organization_name"] == "NewCo"
    assert body["user"]["is_internal"] is True
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] > 0


async def test_signup_rejects_duplicate_email(client: AsyncClient) -> None:
    await signup(client, email="dupe@newco.dev", organization_name="DupeCo")
    response = await client.post(
        "/auth/signup",
        json={
            "email": "dupe@newco.dev",
            "password": SEED_PASSWORD,
            "full_name": "Second",
            "role": "SALES",
            "organization_name": "OtherCo",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


async def test_signup_normalises_email_case(client: AsyncClient) -> None:
    await signup(client, email="mixed@newco.dev", organization_name="MixedCo")
    response = await client.post(
        "/auth/signup",
        json={
            "email": "MIXED@NewCo.DEV",
            "password": SEED_PASSWORD,
            "full_name": "Clash",
            "role": "SALES",
            "organization_name": "ClashCo",
        },
    )
    assert response.status_code == 409


async def test_signup_rejects_customer_role_in_seller_org(
    client: AsyncClient,
) -> None:
    """A portal role inside a seller org would break the isolation model."""
    response = await client.post(
        "/auth/signup",
        json={
            "email": "bad@newco.dev",
            "password": SEED_PASSWORD,
            "full_name": "Bad Pairing",
            "role": "CUSTOMER",
            "organization_name": "SellerCo",
            "organization_kind": "SELLER",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ROLE_ORG_MISMATCH"


async def test_signup_requires_an_organization(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/signup",
        json={
            "email": "orphan@newco.dev",
            "password": SEED_PASSWORD,
            "full_name": "Orphan",
            "role": "SALES",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ORGANIZATION_REQUIRED"


@pytest.mark.parametrize("password", ["short", "allletters", "12345678"])
async def test_signup_rejects_weak_passwords(
    client: AsyncClient, password: str
) -> None:
    response = await client.post(
        "/auth/signup",
        json={
            "email": f"weak-{password}@newco.dev",
            "password": password,
            "full_name": "Weak",
            "role": "SALES",
            "organization_name": "WeakCo",
        },
    )
    assert response.status_code == 422


async def test_login_succeeds_and_records_last_login(client: AsyncClient) -> None:
    await signup(client, email="login@newco.dev", organization_name="LoginCo")
    api = await login(client, "login@newco.dev")
    me = (await api.get("/users/me", expect=200)).json()
    assert me["email"] == "login@newco.dev"
    assert me["last_login_at"] is not None


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    await signup(client, email="pw@newco.dev", organization_name="PwCo")
    response = await client.post(
        "/auth/login", json={"email": "pw@newco.dev", "password": "Wrong123!"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_login_does_not_leak_whether_an_email_exists(
    client: AsyncClient,
) -> None:
    await signup(client, email="known@newco.dev", organization_name="KnownCo")
    wrong_pw = await client.post(
        "/auth/login", json={"email": "known@newco.dev", "password": "Nope123!"}
    )
    unknown = await client.post(
        "/auth/login", json={"email": "ghost@newco.dev", "password": "Nope123!"}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_protected_route_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_protected_route_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.get(
        "/users/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


async def test_refresh_returns_a_new_token_pair(client: AsyncClient) -> None:
    body = await signup(client, email="refresh@newco.dev", organization_name="RefCo")
    refresh_token = body["tokens"]["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    tokens = response.json()
    assert tokens["access_token"]

    me = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200


async def test_access_token_cannot_be_used_as_refresh_token(
    client: AsyncClient,
) -> None:
    body = await signup(client, email="swap@newco.dev", organization_name="SwapCo")
    response = await client.post(
        "/auth/refresh", json={"refresh_token": body["tokens"]["access_token"]}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WRONG_TOKEN_TYPE"


async def test_refresh_token_cannot_be_used_as_access_token(
    client: AsyncClient,
) -> None:
    body = await signup(client, email="swap2@newco.dev", organization_name="Swap2Co")
    response = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {body['tokens']['refresh_token']}"},
    )
    assert response.status_code == 401


async def test_health_endpoint_reports_database_up(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    # The global audit subscriber must be registered or nothing gets logged.
    assert body["event_handlers"]["*"] >= 1


async def test_openapi_document_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "DealFlow360"
    assert "/portal/quotes/{quote_id}/confirm" in schema["paths"]
    docs = await client.get("/docs")
    assert docs.status_code == 200
