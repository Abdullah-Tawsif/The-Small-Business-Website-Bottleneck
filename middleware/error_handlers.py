import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_SAFE_VALIDATION_MESSAGES = {
    "missing": "This field is required.",
    "string_too_short": "This value is too short.",
    "string_too_long": "This value is too long.",
    "string_pattern_mismatch": "This value has an invalid format.",
    "extra_forbidden": "This field is not allowed.",
    "greater_than": "This value is below the allowed minimum.",
    "greater_than_equal": "This value is below the allowed minimum.",
    "less_than": "This value exceeds the allowed maximum.",
    "less_than_equal": "This value exceeds the allowed maximum.",
    "int_parsing": "Enter a whole number.",
    "float_parsing": "Enter a valid number.",
    "decimal_parsing": "Enter a valid number.",
    "value_error": "Invalid value.",
}


def register_error_handlers(app: FastAPI) -> None:
    """Register predictable client errors and non-leaking server errors."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Keep field-level feedback useful without returning submitted values or
        # validation context, which may contain passwords or personal data.
        errors = [
            {
                "loc": list(error.get("loc", ())),
                "msg": _SAFE_VALIDATION_MESSAGES.get(
                    error.get("type"),
                    "Invalid input.",
                ),
                "type": (
                    error.get("type")
                    if error.get("type") in _SAFE_VALIDATION_MESSAGES
                    else "value_error"
                ),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": errors or "Invalid request data."},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        if request.method == "GET":
            if request.url.path in {"/dashboard", "/admin"} and exc.status_code == 401:
                return RedirectResponse(url="/login", status_code=303)
            if request.url.path == "/admin" and exc.status_code == 403:
                return RedirectResponse(url="/dashboard", status_code=303)

        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        # Log server-side for debugging; never return exception text to clients.
        logger.exception("Unhandled application error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )
