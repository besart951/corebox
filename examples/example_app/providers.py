from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app_foundation.auth.oauth import OAuthService
from app_foundation.auth.oauth.api import create_oauth_router
from app_foundation.auth.oauth.state import SqlAlchemyOAuthStateRepository
from app_foundation.billing import BillingService
from app_foundation.billing.api import create_billing_router
from app_foundation.billing.sqlalchemy import SqlAlchemyBillingRepository
from app_foundation.config import GoogleOAuthSettings, StripeSettings

from .container import Composition


def install_providers(app: FastAPI, composition: Composition) -> None:
    settings = composition.settings
    if settings.stripe_enabled:
        from app_foundation.billing.providers.stripe import StripePaymentProvider

        stripe_settings = StripeSettings(_env_file=".env")

        @asynccontextmanager
        async def billing() -> AsyncIterator[BillingService]:
            provider = StripePaymentProvider(stripe_settings)
            try:
                async with composition.operation() as operation:
                    yield BillingService(
                        SqlAlchemyBillingRepository(operation.session),
                        provider,
                        composition.ids,
                        composition.clock,
                        operation.events,
                    )
            finally:
                await provider.close()

        app.include_router(
            create_billing_router(
                billing,
                composition.authorize,
                settings.public_url + "/billing/success",
                settings.public_url + "/billing/cancel",
                settings.billing_price_ids,
            )
        )

    if settings.google_enabled:
        import httpx

        from app_foundation.auth.oauth.google import GoogleOAuthProvider

        @asynccontextmanager
        async def oauth() -> AsyncIterator[OAuthService]:
            async with httpx.AsyncClient() as client, composition.operation() as operation:
                yield OAuthService(
                    operation.auth,
                    operation.users,
                    GoogleOAuthProvider(GoogleOAuthSettings(_env_file=".env"), client),
                    composition.clock,
                    settings.encryption_key.get_secret_value().encode(),
                    SqlAlchemyOAuthStateRepository(operation.session),
                )

        app.include_router(create_oauth_router(oauth, composition.authenticate))
