"""Optional HTTP integration; applications choose their routers."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import override
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app_foundation.access_control import Principal, Resource
from app_foundation.auth import InvalidCredentials
from app_foundation.auth.models import RateLimitExceeded
from app_foundation.observability import request_id
from app_foundation.primitives import (
    Conflict,
    FoundationError,
    InfrastructureUnavailable,
    NotFound,
    PermissionDenied,
    ValidationError,
)

type Scope[T] = Callable[[], AbstractAsyncContextManager[T]]
type Authenticate = Callable[[str], Awaitable[Principal]]
type Authorize = Callable[[str, str, Resource], Awaitable[Principal]]


def bearer(header: str) -> str:
    scheme, separator, token = header.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        raise InvalidCredentials("Bearer authentication required")
    return token


def install_exception_handlers(app: FastAPI) -> None:
    async def handle(_request: Request, error: Exception) -> JSONResponse:
        match error:
            case InvalidCredentials():
                return JSONResponse(
                    {"detail": "Invalid credentials"}, 401, headers={"WWW-Authenticate": "Bearer"}
                )
            case PermissionDenied():
                status = 403
            case NotFound():
                status = 404
            case Conflict():
                status = 409
            case ValidationError():
                status = 422
            case RateLimitExceeded():
                return JSONResponse(
                    {"detail": "Too many attempts"}, 429, headers={"Retry-After": "60"}
                )
            case InfrastructureUnavailable():
                return JSONResponse({"detail": "Service unavailable"}, 503)
            case _:
                return JSONResponse({"detail": "Operation failed"}, 500)
        return JSONResponse({"detail": str(error)}, status)

    app.add_exception_handler(FoundationError, handle)


class RequestIdMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation = uuid4().hex
        context = request_id.set(correlation)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = correlation
            return response
        finally:
            request_id.reset(context)


__all__ = (
    "Authenticate",
    "Authorize",
    "RequestIdMiddleware",
    "Scope",
    "bearer",
    "install_exception_handlers",
)
