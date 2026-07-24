"""The common response envelope every API route wraps its data in, per
explicit instruction:

    { "data": ..., "meta": { "as_of": ..., "freshness": ..., "request_id": ... } }

`Meta.as_of` is wall-clock analysis time (when this response was
computed), not the underlying data's own recency -- the same
distinction already established and disclosed for
`EngineResultEnvelope.as_of` (src/analysis/composite/types.py) and
reused here for consistency rather than inventing a second meaning for
the same word at the API boundary. `Meta.freshness` is the separate,
already-existing `Freshness` classification
(`src.analysis.composite.types.classify_freshness`), reused directly,
never recomputed with new logic.
"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    as_of: datetime
    freshness: str
    request_id: str


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class ListEnvelope(BaseModel, Generic[T]):
    data: List[T]
    meta: Meta
    pagination: PaginationMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
