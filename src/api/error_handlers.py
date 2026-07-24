"""Global exception handlers for this milestone's new routes.

Registered for `APIError` (this milestone's own exception type),
`ValueError` (the documented failure mode of, e.g.,
`TechnicalAnalysisEngine.analyze()` on too little history -- mapped to
422, a client-facing "not enough data yet" condition, not a 500 server
fault), and a final `Exception` catch-all safety net.

None of these intercept `fastapi.HTTPException` -- FastAPI's own
built-in handler for it is left completely untouched, so every
pre-existing route in main.py keeps returning exactly the
`{"detail": "..."}` shape `tests/unit/test_main_error_handling.py`
already verifies, unchanged. See src/api/exceptions.py's module
docstring for the full reasoning.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.exceptions import APIError
from src.api.middleware.request_id import get_request_id

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, get_request_id(request)),
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", str(exc), get_request_id(request)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.error("Unhandled exception (request_id=%s): %s", request_id, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred", request_id),
        )
