import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app_foundation.api import install_exception_handlers
from app_foundation.auth import TokenPair
from app_foundation.auth.api import create_auth_router, create_mfa_router
from app_foundation.identity.api import create_user_router
from app_foundation.notification.api import create_notification_router
from app_foundation.organization.api import create_organization_router, create_team_router
from tests.integration.test_postgres import composition, registered

pytestmark = pytest.mark.postgres


async def test_http_auth_users_orgs_notifications_and_scope(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    services = composition(database)
    user_id = await registered(services)
    await services.seed_roles()
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(create_auth_router(services.auth))
    app.include_router(create_mfa_router(services.mfa, services.authenticate, "Tests"))
    app.include_router(create_user_router(services.users, services.authorize))
    app.include_router(
        create_organization_router(
            services.organizations, services.authenticate, services.authorize, services.users
        )
    )
    app.include_router(create_team_router(services.organizations, services.authorize))
    app.include_router(create_notification_router(services.notifications, services.authorize))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(f"/users/{user_id}")).status_code == 401
        response = await client.post(
            "/auth/login", json={"email": "person@example.com", "password": "correct-password"}
        )
        assert response.status_code == 200, response.text
        pair = TokenPair(**response.json())
        client.headers["Authorization"] = "Bearer " + pair.access_token
        assert (await client.get(f"/users/{user_id}")).status_code == 200
        response = await client.post("/organizations", json={"name": "Organization"})
        assert response.status_code == 201, response.text
        organization_id = response.json()["id"]
        assert (
            await client.post(f"/organizations/{organization_id}/teams", json={"name": "Team"})
        ).status_code == 201
        assert (
            await client.get(f"/organizations/{organization_id}/notifications")
        ).status_code == 200
        assert (await client.get(f"/organizations/{organization_id}")).status_code == 200
        async with services.operation() as operation:
            other = await operation.users.create("other@example.com", "Other")
            other_pair = await operation.auth.create_session(other.id)
        other_headers = {"Authorization": "Bearer " + other_pair.access_token}
        assert (
            await client.get(f"/organizations/{organization_id}", headers=other_headers)
        ).status_code == 403
        invited = await client.post(
            f"/organizations/{organization_id}/invitations", json={"email": other.email}
        )
        assert invited.status_code == 201
        accepted = await client.post(
            "/organizations/invitations/accept",
            json={"token": invited.json()["token"]},
            headers=other_headers,
        )
        assert accepted.status_code == 200, accepted.text
        assert (
            await client.get(f"/organizations/{organization_id}", headers=other_headers)
        ).status_code == 200
        suspended = await client.put(
            f"/organizations/{organization_id}/members/{other.id}/state",
            json={"state": "suspended"},
        )
        assert suspended.status_code == 200
        assert (
            await client.get(f"/organizations/{organization_id}", headers=other_headers)
        ).status_code == 403
        assert (
            await client.post("/auth/refresh", json={"token": pair.refresh_token})
        ).status_code == 200
        assert (
            await client.post("/auth/refresh", json={"token": pair.refresh_token})
        ).status_code == 401
        assert (await client.get(f"/users/{user_id}")).status_code == 401


async def test_example_lifespan_and_database_health(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    from sqlalchemy import text

    from examples.example_app.main import create_app

    services = composition(database)
    async with database[0].connect() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
    assert isinstance(schema, str)
    url = database[0].url.update_query_dict({"options": f"-csearch_path={schema}"})
    settings = services.settings.model_copy(
        update={"database_url": SecretStr(url.render_as_string(hide_password=False))}
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert len(response.headers["X-Request-ID"]) == 32
