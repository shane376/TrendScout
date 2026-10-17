"""Run `python -m trendscout.ingestion.demo`; uses only disposable synthetic data."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .models import CollectionRequest, RetentionPolicy
from .repository import IngestionRepository
from .synthetic import SyntheticSource


def run_demo() -> dict[str, dict[str, int]]:
    now = datetime.now(timezone.utc)
    source = SyntheticSource(clock=lambda: now)
    request = CollectionRequest(source_id=source.source_id, query="synthetic offline example", limit=3)
    first = source.collect(request)
    policy = RetentionPolicy(source_id=source.source_id, ttl=timedelta(hours=2))
    later = now + timedelta(minutes=1)
    second = SyntheticSource(clock=lambda: later).collect(request)
    with TemporaryDirectory(prefix="trendscout-ingestion-") as directory:
        with IngestionRepository(Path(directory) / "demo.sqlite3", [policy]) as repository:
            repository.save(first, now=now)
            repository.save(first, now=now)  # Same-run retry is a no-op.
            assert repository.counts()["collection_runs"] == 1
            repository.save(second, now=later)
            before = repository.counts()
            assert before["content_items"] == 3 and before["collection_runs"] == 2
            item = repository.get_item("synthetic", "fixture-1", source.source_id, now=later)
            assert item is not None and item.collected_at == later
            assert len(repository.get_observations(item.item_id, source.source_id, now=later)) == 2
            first_purge = repository.purge_expired(now=now + policy.ttl)
            assert first_purge["run_items"] == 3 and first_purge["metric_observations"] == 2
            assert first_purge["content_items"] == 0  # Later collection still retained.
            repository.purge_expired(now=later + policy.ttl)
            after = repository.counts()
            assert after == {
                "content_items": 0, "item_records": 0, "collection_runs": 2,
                "run_items": 0, "metric_observations": 0,
            }
            assert repository.get_run(first.run.run_id) == first.run
    return {"before_expiration": before, "first_purge": first_purge, "after_expiration": after}


if __name__ == "__main__":
    print("Synthetic offline ingestion only; not live collection or market evidence.")
    print(json.dumps(run_demo(), indent=2))
    print("Temporary SQLite database removed.")
