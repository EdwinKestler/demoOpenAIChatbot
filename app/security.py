"""Authentication and request validation helpers."""

from __future__ import annotations

import secrets
from typing import Mapping

from decouple import config
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from twilio.request_validator import RequestValidator

_http_basic = HTTPBasic(auto_error=False)


def _twilio_auth_token() -> str:
    return config("TWILIO_AUTH_TOKEN", default="")


def twilio_signature_enabled() -> bool:
    return config("TWILIO_VALIDATE_SIGNATURE", cast=bool, default=True)


def _webhook_url(request: Request) -> str:
    public_base = config("PUBLIC_BASE_URL", default="").strip().rstrip("/")
    if public_base:
        return f"{public_base}{request.url.path}"
    return str(request.url)


async def validate_twilio_signature(request: Request, form: Mapping[str, object]) -> None:
    if not twilio_signature_enabled():
        return

    auth_token = _twilio_auth_token()
    if not auth_token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured")

    signature = request.headers.get("X-Twilio-Signature", "")
    params = {key: str(value) for key, value in form.items()}
    validator = RequestValidator(auth_token)
    if not validator.validate(_webhook_url(request), params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def verify_admin(credentials: HTTPBasicCredentials | None = Depends(_http_basic)) -> str:
    username = config("ADMIN_USERNAME", default="")
    password = config("ADMIN_PASSWORD", default="")
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    valid_user = secrets.compare_digest(credentials.username, username)
    valid_pass = secrets.compare_digest(credentials.password, password)
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class LimitBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > self.max_bytes:
                        return JSONResponse(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            content={"detail": "Request body too large"},
                        )
                except ValueError:
                    pass
        return await call_next(request)