"""Fake aiohttp session/response doubles shared by the SAHMK test modules.

No real socket is ever opened -- SahmkClient's session is injected via
its `session=` constructor argument, so these fakes are all any test
needs to exercise the request/response/error-mapping logic.
"""

from typing import Any, List, Optional, Union


class FakeResponse:
    def __init__(
        self,
        status: int,
        json_body: Any = None,
        text_body: Optional[str] = None,
        headers: Optional[dict] = None,
        raise_on_json: bool = False,
    ):
        self.status = status
        self._json_body = json_body
        self._text_body = text_body if text_body is not None else str(json_body or "")
        self.headers = headers or {}
        self._raise_on_json = raise_on_json

    async def json(self):
        if self._raise_on_json:
            raise ValueError("response body is not valid JSON")
        return self._json_body

    async def text(self):
        return self._text_body


class _GetContextManager:
    def __init__(self, outcome: Union[FakeResponse, BaseException]):
        self._outcome = outcome

    async def __aenter__(self):
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    """Replays `outcomes` in order, one per `.get()` call."""

    def __init__(self, outcomes: List[Union[FakeResponse, BaseException]]):
        self._outcomes = list(outcomes)
        self.calls: List[dict] = []
        self.closed = False

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if not self._outcomes:
            raise AssertionError("FakeSession.get() called more times than outcomes were queued")
        return _GetContextManager(self._outcomes.pop(0))

    async def close(self):
        self.closed = True
