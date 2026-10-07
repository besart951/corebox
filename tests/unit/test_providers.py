import hashlib
import hmac
import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import ClassVar, override
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import stripe
from pydantic import SecretStr

from app_foundation.auth import InvalidCredentials
from app_foundation.auth.oauth.google import GoogleOAuthProvider
from app_foundation.billing import SubscriptionState
from app_foundation.billing.providers.stripe import StripePaymentProvider
from app_foundation.communication.email import EmailAddress, EmailAttachment, EmailMessage
from app_foundation.communication.email.smtp import SmtpEmailSender
from app_foundation.communication.whatsapp import WhatsAppMessage
from app_foundation.communication.whatsapp.providers.meta import MetaWhatsAppSender
from app_foundation.config import GoogleOAuthSettings, StripeSettings, WhatsAppSettings
from app_foundation.primitives import InfrastructureUnavailable, ValidationError


class MockStripeHTTPClient(stripe.HTTPClient):
    name: ClassVar[str] = "mock"

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        super().__init__()
        self._handler = handler

    @override
    async def request_async(
        self, method: str, url: str, headers: Mapping[str, str], post_data: object = None
    ) -> tuple[bytes, int, Mapping[str, str]]:
        assert post_data is None or isinstance(post_data, str | bytes)
        response = self._handler(httpx.Request(method, url, headers=headers, content=post_data))
        return response.content, response.status_code, response.headers

    @override
    async def close_async(self) -> None:
        return None


async def test_stripe_requests_mapping_idempotency_and_signature() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/customers"):
            return httpx.Response(200, json={"id": "cus_1", "object": "customer"})
        if "/checkout/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": "cs_1",
                    "object": "checkout.session",
                    "url": "https://checkout.stripe.com/test",
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "sub_1",
                "object": "subscription",
                "customer": "cus_1",
                "status": "canceled" if request.method == "DELETE" else "active",
            },
        )

    transport = MockStripeHTTPClient(handler)
    provider = StripePaymentProvider(
        StripeSettings(
            secret_key=SecretStr("sk_test_fake"), webhook_secret=SecretStr("webhook-test")
        ),
        transport,
    )
    try:
        assert await provider.create_customer("test@example.com", "customer-key") == "cus_1"
        assert requests[-1].headers["Idempotency-Key"] == "customer-key"
        session = await provider.checkout(
            "cus_1",
            "price_1",
            "https://example.com/success",
            "https://example.com/cancel",
            "checkout-key",
        )
        assert session.provider_id == "cs_1"
        assert (
            await provider.create_subscription("cus_1", "price_1", "subscribe-key")
        ).state == SubscriptionState.ACTIVE
        assert (await provider.cancel("sub_1")).state == SubscriptionState.CANCELED
        payload = json.dumps(
            {
                "id": "evt_1",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": "sub_1"}},
            }
        ).encode()
        timestamp = int(time.time())
        signature = hmac.new(
            b"webhook-test", str(timestamp).encode() + b"." + payload, hashlib.sha256
        ).hexdigest()
        event = provider.verify_webhook(payload, f"t={timestamp},v1={signature}")
        assert event.subscription_provider_id == "sub_1"
        with pytest.raises(ValidationError):
            provider.verify_webhook(payload + b" ", f"t={timestamp},v1={signature}")
    finally:
        await provider.close()


async def test_google_code_exchange_nonce_and_verified_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def verify(_token: str, _request: object, audience: str) -> dict[str, object]:
        assert audience == "client-id"
        return {
            "sub": "subject",
            "email": "person@example.com",
            "email_verified": True,
            "nonce": "nonce",
            "name": "Person",
        }

    monkeypatch.setattr("app_foundation.auth.oauth.google.verify_oauth2_token", verify)

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"code_verifier=verifier" in request.content
        return httpx.Response(200, json={"id_token": "signed-token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleOAuthProvider(
            GoogleOAuthSettings(
                client_id="client-id",
                client_secret=SecretStr("client-secret"),
                redirect_uri="https://example.com/callback",
            ),
            client,
        )
        query = parse_qs(urlparse(provider.authorization_url("state", "challenge", "nonce")).query)
        assert query["code_challenge_method"] == ["S256"]
        assert (await provider.authenticate("code", "verifier", "nonce")).email_verified
        with pytest.raises(InvalidCredentials):
            await provider.authenticate("code", "verifier", "wrong-nonce")


async def test_meta_template_and_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        assert data["template"]["components"][0]["parameters"][0]["text"] == "Ada"
        return httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})

    settings = WhatsAppSettings(
        access_token=SecretStr("meta-token"), phone_number_id="12345", api_version="v23.0"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = MetaWhatsAppSender(settings, client)
        assert (
            await sender.send(
                WhatsAppMessage("+41791234567", template="hello", parameters=("Ada",))
            )
            == "wamid.test"
        )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        with pytest.raises(InfrastructureUnavailable):
            await MetaWhatsAppSender(settings, client).send(
                WhatsAppMessage("+41791234567", "Hello")
            )


def test_email_mime_attachments_and_hidden_bcc() -> None:
    message = EmailMessage(
        EmailAddress("sender@example.com"),
        (EmailAddress("recipient@example.com"),),
        "Hello",
        "Text",
        "<p>HTML</p>",
        bcc=(EmailAddress("hidden@example.com"),),
        attachments=(EmailAttachment("file.txt", b"attachment", "text/plain"),),
    )
    mime = SmtpEmailSender.mime(message)
    assert "Bcc" not in mime
    assert "hidden@example.com" not in mime.as_string()
    assert len(tuple(mime.iter_attachments())) == 1


def test_provider_settings_ignore_other_features_in_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "EXAMPLE_GOOGLE_ENABLED=true\nFOUNDATION_GOOGLE_CLIENT_ID=client\nFOUNDATION_GOOGLE_CLIENT_SECRET=secret\nFOUNDATION_GOOGLE_REDIRECT_URI=https://example.com/callback\n"
    )
    settings = GoogleOAuthSettings(_env_file=dotenv)
    assert settings.client_id == "client"
