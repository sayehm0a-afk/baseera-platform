"""Registers a single consistent error JSON shape for every APIError
subclass: {"error": {"code": "...", "message": "..."}}. Nothing about
FastAPI's own validation-error (422) or generic-exception handling is
touched here -- this only covers the API layer's own, deliberately
raised exceptions.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.exceptions import APIError

logger = logging.getLogger(__name__)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("API error on %s %s: %s", request.method, request.url.path, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, api_error_handler)
