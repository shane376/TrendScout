"""Small explicit offline fixture adapter, unrelated to legacy demo ranking."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from .base import CollectionError
from .models import CollectionRequest, CollectionResult, CollectionRun, ContentItem, NativeMetrics, as_utc


class SyntheticSource:
    source_id = "synthetic.fixture"

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, request: CollectionRequest) -> CollectionResult:
        request = CollectionRequest.model_validate(request.model_dump())
        if request.source_id != self.source_id:
            raise CollectionError(self.source_id, "wrong_source")
        now = as_utc(self._clock())
        items = tuple(ContentItem(
            platform="synthetic", external_id=f"fixture-{number}", source_id=self.source_id,
            provenance="synthetic", attribution="TrendScout synthetic fixture (not live evidence)",
            content_type="discussion", title=f"Synthetic research question {number}",
            description="An offline test record, not an observed market need.",
            collected_at=now, published_at=now - timedelta(hours=number),
            url=f"https://example.com/trendscout/ingestion/{number}",
            metrics=NativeMetrics(observed_at=now, values={"example_replies": number}) if number != 2 else None,
        ) for number in range(1, min(request.limit, 3) + 1))
        return CollectionResult(run=CollectionRun(
            source_id=self.source_id, provenance="synthetic", started_at=now, completed_at=now,
            requested_limit=request.limit, item_count=len(items),
        ), items=items)
