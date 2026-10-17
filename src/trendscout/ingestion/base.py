"""New adapter contract; the legacy sources.ContentSource is unchanged."""

from typing import Literal, Protocol, runtime_checkable

from .models import CollectionRequest, CollectionResult


class CollectionError(RuntimeError):
    """Only curated messages/codes, never provider response bodies or credentials."""

    def __init__(self, source_id: str, code: Literal["wrong_source", "access_denied", "rate_limited", "unavailable", "invalid_response"]):
        messages = {
            "wrong_source": "Request targets a different source.",
            "access_denied": "Collection access denied; check authorized configuration.",
            "rate_limited": "Source rate limit reached; wait before retrying.",
            "unavailable": "Source temporarily unavailable after bounded attempts.",
            "invalid_response": "Source returned invalid records.",
        }
        if code not in messages:
            raise ValueError("Unsupported collection error code")
        self.source_id = source_id
        self.code = code
        super().__init__(messages[code])


@runtime_checkable
class IngestionSource(Protocol):
    @property
    def source_id(self) -> str: ...

    def collect(self, request: CollectionRequest) -> CollectionResult: ...
