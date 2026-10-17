from datetime import timedelta

import pytest

from trendscout.ingestion.models import CollectionRequest, RetentionPolicy
from trendscout.ingestion.repository import IngestionRepository
from trendscout.ingestion.synthetic import SyntheticSource


@pytest.fixture
def ingestion_batch(now):
    source = SyntheticSource(clock=lambda: now)
    return source.collect(CollectionRequest(source_id=source.source_id, query="offline test", limit=3))


@pytest.fixture
def retention():
    return RetentionPolicy(source_id=SyntheticSource.source_id, ttl=timedelta(hours=2))


@pytest.fixture
def repository(tmp_path, retention):
    with IngestionRepository(tmp_path / "ingestion.sqlite3", policies=[retention]) as repository:
        yield repository
