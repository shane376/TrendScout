from typing import Protocol

from ..models import AnalyzedPost, VideoIdea


class IdeaGenerator(Protocol):
    """Provider boundary for templates or a future optional LLM adapter."""

    def generate(self, posts: list[AnalyzedPost], niche: str, mode: str) -> list[VideoIdea]: ...
