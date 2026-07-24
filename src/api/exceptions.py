"""APIError: the one exception type every route added in this milestone
raises for an expected, client-facing failure (404 unknown symbol, 401
unauthenticated, 422 insufficient data, ...).

Deliberately NOT `fastapi.HTTPException` -- every pre-existing route in
main.py already raises bare `HTTPException` and is tested (`tests/unit/
test_main_error_handling.py`) to receive FastAPI's default
`{"detail": "..."}` response shape. Registering a global exception
handler for `HTTPException` to produce this milestone's `{"error": {...}}`
envelope would change that already-tested, already-working response
shape for every existing route too -- exactly the "do not refactor
working code" / "keep full backward compatibility" this milestone was
scoped under. A distinct exception type keeps the two error shapes
(and the two route generations) independent by construction, not by
convention someone could accidentally violate later.
"""


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class NotFoundError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__(status_code=404, code="NOT_FOUND", message=message)


class UnauthorizedError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__(status_code=401, code="UNAUTHORIZED", message=message)


class InsufficientDataError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__(status_code=422, code="INSUFFICIENT_DATA", message=message)
