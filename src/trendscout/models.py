import html
import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ContentPost(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=1000)
    body: str | None = None
    author: str | None = None
    score: int = 0
    comment_count: int = Field(default=0, ge=0)
    created_at: datetime
    url: HttpUrl
    community: str | None = None

    @field_validator("title", "body", mode="before")
    @classmethod
    def clean_text(cls, value):
        if isinstance(value, str):
            return re.sub(r"\s+", " ", html.unescape(value)).strip()
        return value

    @field_validator("score", "comment_count", mode="before")
    @classmethod
    def missing_metrics(cls, value):
        return 0 if value is None else value

    @field_validator("created_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return value.astimezone(timezone.utc)


class AnalyzedPost(BaseModel):
    post: ContentPost
    engagement_score: float = Field(ge=0, le=100)
    recency_score: float = Field(ge=0, le=100)
    discussion_score: float = Field(ge=0, le=100)
    opportunity_score: float = Field(ge=0, le=100)
    rank: int = Field(ge=1)


class VideoIdea(BaseModel):
    title: str
    target_niche: str
    source_id: str
    source_platform: str
    source_title: str
    source_url: HttpUrl
    content_angle: str
    hook: str
    script: str
    suggested_visuals: list[str]
    call_to_action: str
    opportunity_score: float = Field(ge=0, le=100)
    generation_method: str = "template"
    requires_fact_check: bool = True
    fact_check_note: str = "Source posts are unverified leads. Verify claims and permissions before production."
    mode: str
