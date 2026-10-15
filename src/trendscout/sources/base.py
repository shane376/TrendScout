from typing import Protocol

from ..models import ContentPost


class SourceError(RuntimeError):
    """A safe, user-facing collection failure."""


class ContentSource(Protocol):
    def collect(self, niche: str, candidate_limit: int) -> list[ContentPost]: ...
