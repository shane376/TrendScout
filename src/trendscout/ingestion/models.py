"""Platform-neutral records. Unknown counters remain unavailable, never zero-filled."""

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator,
)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def nonblank_id(value: str) -> str:
    if not value.strip():
        raise ValueError("External identifier must not be blank")
    return value


UtcTime = Annotated[datetime, AfterValidator(as_utc)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ExternalId = Annotated[str, StringConstraints(min_length=1, max_length=2048), AfterValidator(nonblank_id)]
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")]
Counter = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
Limit = Annotated[int, Field(strict=True, ge=1, le=100)]
Provenance = Literal["synthetic", "live", "unknown"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class NativeMetrics(Record):
    """Names retain provider semantics; counters from different platforms are not scores."""

    observed_at: UtcTime
    values: dict[Name, Counter | None] = Field(default_factory=dict)
    expires_at: UtcTime | None = None

    @model_validator(mode="after")
    def valid_expiration(self):
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("Metric expiration must follow observation")
        return self


class ContentItem(Record):
    platform: SourceId
    external_id: ExternalId
    source_id: SourceId
    provenance: Provenance
    attribution: Name
    content_type: Name
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] | None = None
    collected_at: UtcTime
    published_at: UtcTime | None = None
    creator: Name | None = None
    description: Annotated[str, StringConstraints(max_length=10000)] | None = None
    url: HttpUrl | None = None
    community: Name | None = None
    metrics: NativeMetrics | None = None
    expires_at: UtcTime | None = None

    @property
    def item_id(self) -> str:
        """Stable internal identity, independent of adapter and collection run."""
        return str(uuid5(NAMESPACE_URL, json.dumps([self.platform, self.external_id])))

    @model_validator(mode="after")
    def valid_times(self):
        if self.url is not None and (self.url.username is not None or self.url.password is not None):
            raise ValueError("Attribution URLs must not contain credentials")
        if self.expires_at is not None and self.expires_at <= self.collected_at:
            raise ValueError("Content expiration must follow collection")
        if self.metrics is not None and self.metrics.observed_at > self.collected_at:
            raise ValueError("Metrics cannot be observed after item collection")
        return self


class CollectionRequest(Record):
    source_id: SourceId
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    limit: Limit = 25


class CollectionRun(Record):
    run_id: UUID = Field(default_factory=uuid4)
    source_id: SourceId
    provenance: Provenance
    started_at: UtcTime
    completed_at: UtcTime
    requested_limit: Limit
    item_count: Counter
    rejected_count: Counter = 0
    status: Literal["complete", "partial", "failed"] = "complete"
    error_codes: tuple[SourceId, ...] = ()

    @model_validator(mode="after")
    def valid_run(self):
        if self.completed_at < self.started_at:
            raise ValueError("Completion cannot precede start")
        if self.item_count + self.rejected_count > self.requested_limit:
            raise ValueError("Result exceeds requested limit")
        if self.status == "complete" and (self.rejected_count or self.error_codes):
            raise ValueError("Incomplete collection must be explicitly partial or failed")
        if self.status != "complete" and not self.error_codes:
            raise ValueError("Partial/failed runs require safe error codes")
        if self.status == "failed" and self.item_count:
            raise ValueError("Failed runs cannot contain accepted items")
        return self


class CollectionResult(Record):
    run: CollectionRun
    items: tuple[ContentItem, ...] = ()

    @model_validator(mode="after")
    def consistent_batch(self):
        if len(self.items) != self.run.item_count:
            raise ValueError("Item count does not match result")
        identities = set()
        for item in self.items:
            if (item.source_id, item.provenance) != (self.run.source_id, self.run.provenance):
                raise ValueError("Item attribution must match the collection run")
            if not self.run.started_at <= item.collected_at <= self.run.completed_at:
                raise ValueError("Item collection timestamp is outside run interval")
            if item.item_id in identities:
                raise ValueError("Duplicate content identity in batch")
            identities.add(item.item_id)
        return self


class RetentionPolicy(Record):
    source_id: SourceId
    ttl: timedelta
    allow_live: bool = False

    @model_validator(mode="after")
    def finite_retention(self):
        if self.ttl <= timedelta(0):
            raise ValueError("Retention must be a positive duration")
        return self
