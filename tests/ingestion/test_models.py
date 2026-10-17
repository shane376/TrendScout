from datetime import timedelta, timezone

import pytest
from pydantic import ValidationError

from trendscout.ingestion.base import CollectionError, IngestionSource
from trendscout.ingestion.models import (
    CollectionRequest, CollectionResult, ContentItem, NativeMetrics, RetentionPolicy,
)
from trendscout.ingestion.synthetic import SyntheticSource


def test_platform_neutral_identity_and_unavailable_metadata(ingestion_batch, now):
    first = ingestion_batch.items[0]
    other_source = ContentItem.model_validate(first.model_dump() | {"source_id": "another.adapter"})
    assert first.item_id == other_source.item_id
    other_platform = ContentItem.model_validate(first.model_dump() | {"platform": "another"})
    assert first.item_id != other_platform.item_id
    assert ingestion_batch.items[1].metrics is None
    metrics = NativeMetrics(observed_at=now, values={"views": None, "likes": 0})
    assert metrics.values == {"views": None, "likes": 0}
    assert NativeMetrics(observed_at=now).values == {}
    assert first.creator is None and first.community is None
    minimal = ContentItem(
        platform="other", external_id="native-id", source_id="source", provenance="unknown",
        attribution="Provider attribution", content_type="video", collected_at=now,
    )
    assert minimal.title is minimal.description is minimal.url is minimal.published_at is None
    exact_id = ContentItem.model_validate(minimal.model_dump() | {"external_id": " Native-ID "})
    assert exact_id.external_id == " Native-ID "


def test_attribution_url_rejects_embedded_credentials(ingestion_batch):
    data = ingestion_batch.items[0].model_dump()
    data["url"] = "https://username:password@example.com/private"
    with pytest.raises(ValidationError, match="credentials"):
        ContentItem.model_validate(data)


@pytest.mark.parametrize("value", [-1, 1.5, True, "12", 2**63])
def test_invalid_native_counters(now, value):
    with pytest.raises(ValidationError):
        NativeMetrics(observed_at=now, values={"provider_counter": value})


@pytest.mark.parametrize("field", ["collected_at", "published_at", "expires_at"])
def test_content_timestamps_must_be_aware(ingestion_batch, now, field):
    with pytest.raises(ValidationError):
        ContentItem.model_validate(ingestion_batch.items[0].model_dump() | {field: now.replace(tzinfo=None)})


def test_utc_conversion(ingestion_batch, now):
    offset = timezone(timedelta(hours=5, minutes=30))
    data = ingestion_batch.items[0].model_dump()
    data.update(collected_at=now.astimezone(offset), published_at=now.astimezone(offset))
    item = ContentItem.model_validate(data)
    assert item.collected_at == now and item.collected_at.tzinfo == timezone.utc
    assert item.published_at.tzinfo == timezone.utc
    assert NativeMetrics(observed_at=now.astimezone(offset)).observed_at.tzinfo == timezone.utc


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_request_limits(limit):
    with pytest.raises(ValidationError):
        CollectionRequest(source_id="synthetic.fixture", query="test", limit=limit)


@pytest.mark.parametrize("change", [{"source_id": ""}, {"query": " "}, {"api_token": "not-allowed"}])
def test_request_validation(change):
    with pytest.raises(ValidationError):
        CollectionRequest.model_validate({"source_id": "synthetic.fixture", "query": "test"} | change)


@pytest.mark.parametrize("change", [
    {"source_id": "another"}, {"provenance": "live"}, {"collected_at": "2026-10-16T12:00:00Z"},
])
def test_result_requires_consistent_attribution_and_times(ingestion_batch, change):
    data = ingestion_batch.model_dump()
    data["items"][0].update(change)
    with pytest.raises(ValidationError):
        CollectionResult.model_validate(data)


def test_result_rejects_duplicates_counts_and_unmarked_partial(ingestion_batch):
    data = ingestion_batch.model_dump()
    data["items"] = [data["items"][0]] * 3
    with pytest.raises(ValidationError, match="Duplicate"):
        CollectionResult.model_validate(data)
    data = ingestion_batch.model_dump()
    data["run"]["item_count"] = 1
    with pytest.raises(ValidationError, match="count"):
        CollectionResult.model_validate(data)
    data = ingestion_batch.model_dump()
    data["items"] = data["items"][:2]
    data["run"].update(item_count=2, rejected_count=1)
    with pytest.raises(ValidationError, match="partial"):
        CollectionResult.model_validate(data)
    data["run"].update(status="partial", error_codes=("invalid_record",))
    assert CollectionResult.model_validate(data).run.status == "partial"


def test_run_and_metric_time_validation(ingestion_batch, now):
    data = ingestion_batch.model_dump()
    data["run"]["completed_at"] = now - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="Completion"):
        CollectionResult.model_validate(data)
    with pytest.raises(ValidationError):
        NativeMetrics(observed_at=now, expires_at=now)
    with pytest.raises(ValidationError):
        NativeMetrics(observed_at=now.replace(tzinfo=None))
    data = ingestion_batch.items[0].model_dump()
    data["metrics"]["observed_at"] = now + timedelta(seconds=1)
    with pytest.raises(ValidationError, match="after item"):
        ContentItem.model_validate(data)
    data["metrics"] = None
    data["expires_at"] = now
    with pytest.raises(ValidationError, match="expiration"):
        ContentItem.model_validate(data)


def test_synthetic_contract_and_safe_errors(now):
    source = SyntheticSource(clock=lambda: now)
    assert isinstance(source, IngestionSource)
    request = CollectionRequest(source_id=source.source_id, query="not a live trend", limit=1)
    result = source.collect(request)
    assert len(result.items) == 1 and result.run.provenance == "synthetic"
    assert result.run.started_at == result.run.completed_at == now
    assert source.collect(request).run.run_id != result.run.run_id
    with pytest.raises(CollectionError) as error:
        source.collect(request.model_copy(update={"source_id": "other"}))
    assert error.value.code == "wrong_source" and error.value.source_id == source.source_id
    assert "different source" in str(error.value)


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
def test_retention_requires_positive_duration(ttl):
    with pytest.raises(ValidationError):
        RetentionPolicy(source_id="source", ttl=ttl)
