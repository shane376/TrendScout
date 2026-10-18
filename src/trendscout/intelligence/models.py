"""Explainable report contracts; unavailable evidence remains None."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from trendscout.ingestion.models import Counter, Record, UtcTime

Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class RankingConfig(Record):
    freshness_weight: Fraction = .30
    views_weight: Fraction = .35
    likes_weight: Fraction = .20
    comments_weight: Fraction = .15
    freshness_half_life_days: Positive = 30
    exposure_floor_days: Positive = 1
    views_per_day_reference: Positive = 1000
    like_ratio_reference: Positive = .05
    comment_ratio_reference: Positive = .01

    @model_validator(mode="after")
    def positive_weight_total(self):
        if not sum((self.freshness_weight, self.views_weight, self.likes_weight, self.comments_weight)):
            raise ValueError("At least one ranking weight must be positive")
        return self


class VideoSignals(Record):
    age_days: Nonnegative | None = None
    observation_age_days: Nonnegative | None = None
    views: Counter | None = None
    likes: Counter | None = None
    comments: Counter | None = None
    lifetime_average_views_per_day: Nonnegative | None = None
    like_to_view_ratio: Nonnegative | None = None
    comment_to_view_ratio: Nonnegative | None = None
    freshness_score: Score | None = None


class ScoreComponent(Record):
    score: Score | None
    weight: Fraction
    available: bool
    explanation: str

    @model_validator(mode="after")
    def consistent_availability(self):
        if self.available != (self.score is not None):
            raise ValueError("Component availability must match its score")
        return self


class DataCompleteness(Record):
    available_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    fraction: Fraction


class Opportunity(Record):
    lens: Literal["creator", "business"]
    interpretation: str
    evidence: tuple[str, ...]
    limitation: str


class RankedVideo(Record):
    rank: int = Field(ge=1)
    external_id: str
    source_id: str
    title: str | None
    source_url: str | None
    published_at: UtcTime | None
    observed_at: UtcTime | None
    signals: VideoSignals
    components: dict[str, ScoreComponent]
    research_priority_score: Score | None
    completeness: DataCompleteness
    explanation: str
    warnings: tuple[str, ...]
    creator: Opportunity | None
    business: Opportunity | None


class IntelligenceReport(Record):
    source_id: str
    provenance: Literal["synthetic", "live"]
    collection_status: Literal["complete", "partial", "failed"]
    as_of: UtcTime
    config: RankingConfig
    videos: tuple[RankedVideo, ...]
    excluded_count: int = Field(ge=0)
    warnings: tuple[str, ...]
