import asyncio
import json

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from middleware.error_handlers import register_error_handlers


def test_validation_handler_returns_field_messages_without_input_values():
    app = FastAPI()
    register_error_handlers(app)
    handler = app.exception_handlers[RequestValidationError]
    exception = RequestValidationError([
        {
            "type": "string_too_short",
            "loc": ("body", "password"),
            "msg": "Value private-password-value is too short.",
            "input": "private-password-value",
            "ctx": {"min_length": 10, "received": "private-password-value"},
        },
        {
            "type": "value_error",
            "loc": ("body", "email"),
            "msg": "Invalid address private-email-value.",
            "input": "private-email-value",
            "ctx": {"received": "private-email-value"},
        }
    ])
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/register",
        "headers": [],
    })

    response = asyncio.run(handler(request, exception))
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload == {
        "detail": [
            {
                "loc": ["body", "password"],
                "msg": "This value is too short.",
                "type": "string_too_short",
            },
            {
                "loc": ["body", "email"],
                "msg": "Invalid value.",
                "type": "value_error",
            },
        ]
    }
    assert "private-password-value" not in response.body.decode()
    assert "private-email-value" not in response.body.decode()
