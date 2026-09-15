"""Stable public error responses for the HTTP boundary."""

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from cliova.api.v1.models import ApiErrorBody, ApiErrorDetail, ApiErrorResponse
from cliova.infrastructure.persistence.postgres import (
    PersistenceError,
    TickConflictError,
    WorldNotFoundError,
)
from cliova.infrastructure.persistence.worlds import WorldAlreadyExistsError

ExceptionHandler = Callable[[Request, Exception], Awaitable[JSONResponse]]


class ApiError(Exception):
    """Intentional public API failure with a stable machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: tuple[ApiErrorDetail, ...] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _response(
    status_code: int,
    code: str,
    message: str,
    details: tuple[ApiErrorDetail, ...] = (),
) -> JSONResponse:
    payload = ApiErrorResponse(
        error=ApiErrorBody(code=code, message=message, details=details)
    ).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=payload)


async def _api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(ApiError, exc)
    return _response(error.status_code, error.code, error.message, error.details)


async def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    validation = cast(RequestValidationError, exc)
    errors = validation.errors()
    query_only = bool(errors) and all(
        error.get("loc", (None,))[0] == "query" for error in errors
    )
    details = tuple(
        ApiErrorDetail(
            location=".".join(str(part) for part in error.get("loc", ())),
            message=str(error.get("msg", "Invalid value")),
            type=str(error.get("type")) if error.get("type") is not None else None,
        )
        for error in errors
    )
    return _response(
        422,
        "invalid_query" if query_only else "invalid_request",
        "Request validation failed.",
        details,
    )


async def _world_not_found_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return _response(404, "world_not_found", "World does not exist.")


async def _world_exists_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return _response(409, "world_exists", "World already exists.")


async def _tick_conflict_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return _response(
        409,
        "tick_conflict",
        "Expected tick does not match the persisted world state.",
    )


async def _persistence_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return _response(500, "persistence_error", "Persistence operation failed.")


def install_error_handlers(app: FastAPI) -> None:
    """Install normalized handlers without exposing raw database/validation exceptions."""

    handlers: tuple[tuple[type[Exception], ExceptionHandler], ...] = (
        (ApiError, _api_error_handler),
        (RequestValidationError, _validation_handler),
        (WorldNotFoundError, _world_not_found_handler),
        (WorldAlreadyExistsError, _world_exists_handler),
        (TickConflictError, _tick_conflict_handler),
        (PersistenceError, _persistence_handler),
    )
    for exception_type, handler in handlers:
        app.add_exception_handler(exception_type, handler)
