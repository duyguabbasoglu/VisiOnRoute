"""API error envelope.

All errors leave the API as::

    {"error": {"code": "...", "message": "<Türkçe mesaj>", "request_id": "..."}}

``code`` is machine-readable and stable; ``message`` is customer-facing
Turkish. Stack traces are never exposed.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from visionroute.application.errors import (
    AccountLockedError,
    ApplicationError,
    DomainConflictError,
    DomainNotFoundError,
    InvalidCredentialsError,
    PermissionDeniedError,
    ValidationFailedError,
)
from visionroute.observability.logging import get_logger

logger = get_logger(__name__)


class ApiError(Exception):
    """Application-level error carrying a stable code and Turkish message."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"
    message: str = "Geçersiz istek."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        self.headers = headers


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "Kayıt bulunamadı."


class UnauthorizedError(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "Kimlik doğrulaması gerekli."


class ForbiddenError(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "Bu işlem için yetkiniz yok."


class ConflictError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "Kayıt mevcut durumla çelişiyor."


class RateLimitedError(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Çok fazla istek gönderildi. Lütfen daha sonra tekrar deneyin."


def _envelope(request: Request, code: str, message: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
    }
    body.update({k: v for k, v in extra.items() if v is not None})
    return {"error": body}


# Application-layer error → (HTTP status, machine-readable code)
_APPLICATION_ERROR_MAP: list[tuple[type[ApplicationError], int, str]] = [
    (ValidationFailedError, status.HTTP_422_UNPROCESSABLE_CONTENT, "VALIDATION_ERROR"),
    (InvalidCredentialsError, status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS"),
    (AccountLockedError, status.HTTP_403_FORBIDDEN, "ACCOUNT_LOCKED"),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN, "FORBIDDEN"),
    (DomainConflictError, status.HTTP_409_CONFLICT, "CONFLICT"),
    (DomainNotFoundError, status.HTTP_404_NOT_FOUND, "NOT_FOUND"),
]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def _application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        for error_type, http_status, code in _APPLICATION_ERROR_MAP:
            if isinstance(exc, error_type):
                details = (
                    [{"message": p} for p in exc.problems]
                    if isinstance(exc, ValidationFailedError)
                    else None
                )
                return JSONResponse(
                    status_code=http_status,
                    content=_envelope(request, code, str(exc), details=details),
                )
        logger.exception("unmapped_application_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(request, "INTERNAL_ERROR", "Beklenmeyen bir hata oluştu."),
        )

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, exc.code, exc.message, details=exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "type": err["type"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope(
                request,
                "VALIDATION_ERROR",
                "Gönderilen veriler doğrulanamadı. Lütfen alanları kontrol edin.",
                details=details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "RATE_LIMITED",
        }.get(exc.status_code, "HTTP_ERROR")
        message = {
            401: "Kimlik doğrulaması gerekli.",
            403: "Bu işlem için yetkiniz yok.",
            404: "Kayıt bulunamadı.",
            405: "Bu yöntem desteklenmiyor.",
            429: "Çok fazla istek gönderildi.",
        }.get(exc.status_code, "İstek işlenemedi.")
        return JSONResponse(status_code=exc.status_code, content=_envelope(request, code, message))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log with stack trace internally; never expose it to the client.
        logger.exception(
            "unhandled_error",
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                request,
                "INTERNAL_ERROR",
                "Beklenmeyen bir hata oluştu. Sorun kaydedildi.",
            ),
        )
