import asyncio
import hmac
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ValidationError
lazy from google.auth.exceptions import GoogleAuthError
lazy from google.auth.transport.requests import Request
lazy from google.oauth2.id_token import verify_oauth2_token

from app_foundation.auth.models import InvalidCredentials, OAuthIdentity
from app_foundation.config import GoogleOAuthSettings
from app_foundation.identity import normalize_email
from app_foundation.primitives import InfrastructureUnavailable


class _TokenResponse(BaseModel):
    id_token: str


class _GoogleClaims(BaseModel):
    sub: str
    email: str
    email_verified: bool
    nonce: str
    name: str = "Google user"


class GoogleOAuthProvider:
    name: str = "google"

    def __init__(self, settings: GoogleOAuthSettings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def authorization_url(self, state: str, challenge: str, nonce: str) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": self._settings.client_id,
                "redirect_uri": self._settings.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    async def authenticate(self, code: str, verifier: str, nonce: str) -> OAuthIdentity:
        try:
            response = await self._client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self._settings.client_id,
                    "client_secret": self._settings.client_secret.get_secret_value(),
                    "redirect_uri": self._settings.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
                timeout=15,
            )
            response.raise_for_status()
            token = _TokenResponse.model_validate_json(response.content)
            claims = await asyncio.to_thread(self._verify, token.id_token)
        except httpx.HTTPStatusError as error:
            raise InvalidCredentials("OAuth exchange rejected") from error
        except (httpx.RequestError, GoogleAuthError) as error:
            raise InfrastructureUnavailable("OAuth provider unavailable") from error
        except (ValueError, ValidationError) as error:
            raise InvalidCredentials("Invalid OAuth identity") from error
        if not hmac.compare_digest(claims.nonce, nonce):
            raise InvalidCredentials("Invalid OAuth nonce")
        return OAuthIdentity(
            self.name, claims.sub, normalize_email(claims.email), claims.email_verified, claims.name
        )

    def _verify(self, token: str) -> _GoogleClaims:
        return _GoogleClaims.model_validate(
            verify_oauth2_token(token, Request(), self._settings.client_id)
        )
