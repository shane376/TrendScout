import sqlite3
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trendscout.ingestion.models import CollectionRequest, CollectionResult, RetentionPolicy
from trendscout.ingestion.repository import IngestionRepository, PersistenceError
from trendscout.ingestion.synthetic import SyntheticSource


def test_persist_reopen_and_replay(tmp_path, ingestion_batch, retention, now):
    database = tmp_path / "test.sqlite3"
    with IngestionRepository(database, [retention]) as repository:
        assert repository.save(ingestion_batch, now=now) == ingestion_batch.run.run_id
        assert repository.save(ingestion_batch, now=now) == ingestion_batch.run.run_id
        assert repository.counts() == {
            "content_items": 3, "item_records": 3, "collection_runs": 1,
            "run_items": 3, "metric_observations": 2,
        }
        assert repository.get_run(ingestion_batch.run.run_id) == ingestion_batch.run
        assert repository.get_run("missing") is None
    with IngestionRepository(database, [retention]) as repository:
        first = repository.get_item("synthetic", "fixture-1", retention.source_id, now=now)
        assert first.title == ingestion_batch.items[0].title
        assert first.item_id == ingestion_batch.items[0].item_id
        assert first.expires_at == now + retention.ttl
        assert first.metrics.values == {"example_replies": 1}
        assert repository.get_item("synthetic", "fixture-2", retention.source_id, now=now).metrics is None


def test_repeated_collection_preserves_identity_and_observations(repository, ingestion_batch, now):
    repository.save(ingestion_batch, now=now)
    later = now + timedelta(hours=1)
    source = SyntheticSource(clock=lambda: later)
    result = source.collect(CollectionRequest(source_id=source.source_id, query="another query", limit=3))
    repository.save(result, now=later)
    assert repository.counts() == {
        "content_items": 3, "item_records": 3, "collection_runs": 2,
        "run_items": 6, "metric_observations": 4,
    }
    observations = repository.get_observations(result.items[0].item_id, source.source_id, now=later)
    assert [observation.observed_at for observation in observations] == [now, later]
    item = repository.get_item("synthetic", "fixture-1", source.source_id, now=later)
    assert item.collected_at == later and item.metrics.observed_at == later


def test_unapproved_persistence_is_disabled(tmp_path, ingestion_batch, retention, now):
    with IngestionRepository(tmp_path / "blocked.sqlite3") as repository:
        with pytest.raises(PersistenceError, match="explicit source policy"):
            repository.save(ingestion_batch, now=now)
        assert not any(repository.counts().values())
    for provenance in ("live", "unknown"):
        data = ingestion_batch.model_dump()
        data["run"]["provenance"] = provenance
        for item in data["items"]:
            item["provenance"] = provenance
        batch = CollectionResult.model_validate(data)
        with IngestionRepository(":memory:", [retention]) as repository:
            with pytest.raises(PersistenceError):
                repository.save(batch, now=now)
        if provenance == "live":
            with IngestionRepository(":memory:", [retention.model_copy(update={"allow_live": True})]) as repository:
                repository.save(batch, now=now)
                assert repository.counts()["content_items"] == 3


def test_invalid_constructed_result_cannot_bypass_validation(repository, ingestion_batch, now):
    bad = ingestion_batch.model_copy(update={"items": ingestion_batch.items[:1]})
    with pytest.raises(ValidationError):
        repository.save(bad, now=now)
    assert not any(repository.counts().values())


def test_partial_and_failed_runs_are_explicit(repository, ingestion_batch, now):
    data = ingestion_batch.model_dump()
    data["items"] = data["items"][:2]
    data["run"].update(item_count=2, rejected_count=1, status="partial", error_codes=["invalid_record"])
    partial = CollectionResult.model_validate(data)
    repository.save(partial, now=now)
    assert repository.get_run(partial.run.run_id).status == "partial"
    failed = CollectionResult(run=partial.run.model_copy(update={
        "run_id": uuid4(), "item_count": 0, "status": "failed", "error_codes": ("access_denied",),
    }))
    repository.save(failed, now=now)
    assert repository.counts()["collection_runs"] == 2
    assert repository.counts()["run_items"] == 2


def test_run_id_cannot_be_reused_with_changed_batch(repository, ingestion_batch, now):
    repository.save(ingestion_batch, now=now)
    data = ingestion_batch.model_dump()
    data["items"][0]["title"] = "Changed record with reused run ID"
    with pytest.raises(PersistenceError, match="Run ID"):
        repository.save(CollectionResult.model_validate(data), now=now)
    assert repository.get_item("synthetic", "fixture-1", ingestion_batch.run.source_id, now=now).title == ingestion_batch.items[0].title


def test_sql_error_rolls_back_whole_batch(repository, ingestion_batch, now):
    repository._connection.execute("""CREATE TRIGGER fail_observation BEFORE INSERT ON metric_observations
        BEGIN SELECT RAISE(ABORT, 'simulated disk write failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="simulated"):
        repository.save(ingestion_batch, now=now)
    assert not any(repository.counts().values())
    assert repository.get_run(ingestion_batch.run.run_id) is None
    repository._connection.execute("DROP TRIGGER fail_observation")
    repository.save(ingestion_batch, now=now)
    assert repository.counts()["content_items"] == 3


def test_metric_conflict_rolls_back_updates(repository, ingestion_batch, now):
    repository.save(ingestion_batch, now=now)
    before = repository.counts()
    data = ingestion_batch.model_dump()
    data["run"]["run_id"] = uuid4()
    data["items"][0]["title"] = "Must roll back"
    data["items"][2]["metrics"]["values"]["example_replies"] = 99
    with pytest.raises(PersistenceError, match="Conflicting metric"):
        repository.save(CollectionResult.model_validate(data), now=now)
    assert repository.counts() == before
    assert repository.get_item("synthetic", "fixture-1", ingestion_batch.run.source_id, now=now).title == ingestion_batch.items[0].title


def test_expiration_purges_relationships_but_keeps_minimal_run(repository, ingestion_batch, retention, now):
    repository.save(ingestion_batch, now=now)
    expired = now + retention.ttl
    assert repository.get_item("synthetic", "fixture-1", retention.source_id, now=expired) is None
    assert repository.get_observations(ingestion_batch.items[0].item_id, retention.source_id, now=expired) == []
    deleted = repository.purge_expired(now=expired)
    assert deleted == {"content_items": 3, "item_records": 3, "collection_runs": 0, "run_items": 3, "metric_observations": 2}
    assert repository.get_run(ingestion_batch.run.run_id) == ingestion_batch.run
    assert repository._connection.execute("SELECT batch_digest FROM collection_runs").fetchone()[0] is None
    assert repository._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not any(repository.purge_expired(now=expired).values())
    with pytest.raises(PersistenceError, match="expired"):
        repository.save(ingestion_batch, now=expired)


def test_source_deadlines_and_early_observation_expiry(repository, ingestion_batch, retention, now):
    data = ingestion_batch.model_dump()
    data["items"][0]["metrics"]["expires_at"] = now + timedelta(minutes=15)
    data["items"][1]["expires_at"] = now + timedelta(minutes=30)
    batch = CollectionResult.model_validate(data)
    repository.save(batch, now=now)
    deleted = repository.purge_expired(now=now + timedelta(minutes=20))
    assert deleted["metric_observations"] == 1 and deleted["content_items"] == 0
    assert repository.get_item("synthetic", "fixture-1", retention.source_id, now=now + timedelta(minutes=20)).metrics is None
    deleted = repository.purge_expired(now=now + timedelta(minutes=30))
    assert deleted["content_items"] == deleted["item_records"] == deleted["run_items"] == 1
    assert repository.counts()["content_items"] == 2


def test_retention_is_independent_per_source(tmp_path, ingestion_batch, retention, now):
    second = RetentionPolicy(source_id="other.fixture", ttl=timedelta(hours=6))
    data = ingestion_batch.model_dump()
    data["run"].update(run_id=uuid4(), source_id=second.source_id)
    for item in data["items"]:
        item["source_id"] = second.source_id
    with IngestionRepository(tmp_path / "sources.sqlite3", [retention, second]) as repository:
        repository.save(ingestion_batch, now=now)
        repository.save(CollectionResult.model_validate(data), now=now)
        assert repository.counts()["content_items"] == 3
        assert repository.counts()["item_records"] == 6
        repository.purge_expired(now=now + retention.ttl)
        assert repository.counts()["content_items"] == 3
        assert repository.counts()["item_records"] == 3
        assert repository.get_item("synthetic", "fixture-1", second.source_id, now=now + retention.ttl) is not None
        repository.purge_expired(now=now + second.ttl)
        assert repository.counts()["content_items"] == 0


def test_foreign_keys_and_parameterized_values(repository, ingestion_batch, now):
    assert repository._connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute("INSERT INTO item_records VALUES (?, ?, ?, ?, ?)", ("missing", "source", "a", "b", "{}"))
    data = ingestion_batch.model_dump()
    data["items"][0]["external_id"] = "x'); DROP TABLE collection_runs; --"
    repository.save(CollectionResult.model_validate(data), now=now)
    assert repository.get_item("synthetic", data["items"][0]["external_id"], ingestion_batch.run.source_id, now=now)
    assert repository.counts()["collection_runs"] == 1


def test_schema_versioning_and_unknown_database(tmp_path):
    path = tmp_path / "version.sqlite3"
    with IngestionRepository(path) as repository:
        assert repository._connection.execute("PRAGMA user_version").fetchone()[0] == 1
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(PersistenceError, match="Unsupported"):
        IngestionRepository(path)
    other = tmp_path / "unversioned.sqlite3"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    with pytest.raises(PersistenceError, match="unversioned"):
        IngestionRepository(other)


def test_failed_migration_rolls_back_schema(tmp_path, monkeypatch):
    import trendscout.ingestion.repository as module

    path = tmp_path / "migration.sqlite3"
    monkeypatch.setattr(module, "MIGRATION_1", ("CREATE TABLE temporary_table (id INTEGER)", "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        IngestionRepository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_expired_or_future_batches_cannot_be_stored(repository, ingestion_batch, retention, now):
    with pytest.raises(PersistenceError, match="expired"):
        repository.save(ingestion_batch, now=now + retention.ttl)
    with pytest.raises(PersistenceError, match="after persistence"):
        repository.save(ingestion_batch, now=now - timedelta(seconds=1))
    assert not any(repository.counts().values())


def test_purge_rolls_back_on_database_error(repository, ingestion_batch, retention, now):
    repository.save(ingestion_batch, now=now)
    before = repository.counts()
    repository._connection.execute("""CREATE TRIGGER fail_purge BEFORE DELETE ON item_records
        BEGIN SELECT RAISE(ABORT, 'purge interrupted'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="purge interrupted"):
        repository.purge_expired(now=now + retention.ttl)
    assert repository.counts() == before
    assert repository._connection.execute("SELECT batch_digest FROM collection_runs").fetchone()[0] is not None


def test_empty_run_replay_after_purge(repository, ingestion_batch, now):
    empty = CollectionResult(run=ingestion_batch.run.model_copy(update={"item_count": 0}))
    repository.save(empty, now=now)
    repository.purge_expired(now=now)
    assert repository.save(empty, now=now) == empty.run.run_id
    assert repository.counts()["collection_runs"] == 1


def test_content_expiry_caps_observations_and_purged_replay(repository, ingestion_batch, now):
    data = ingestion_batch.model_dump()
    for item in data["items"]:
        item["expires_at"] = now + timedelta(minutes=10)
    batch = CollectionResult.model_validate(data)
    repository.save(batch, now=now)
    observation = repository.get_observations(batch.items[0].item_id, batch.run.source_id, now=now)[0]
    assert observation.expires_at == now + timedelta(minutes=10)
    repository.purge_expired(now=now + timedelta(minutes=10))
    # Even a backdated delivery cannot resurrect a purged nonempty run with the same ID.
    with pytest.raises(PersistenceError, match="expired batch data"):
        repository.save(batch, now=now)


def test_retention_is_based_on_observation_time(repository, ingestion_batch, retention, now):
    data = ingestion_batch.model_dump()
    data["items"][0]["metrics"]["observed_at"] = now - retention.ttl
    with pytest.raises(PersistenceError, match="expired"):
        repository.save(CollectionResult.model_validate(data), now=now)
    assert not any(repository.counts().values())


def test_duplicate_policies_rejected(retention):
    with pytest.raises(ValueError, match="Duplicate retention policy"):
        IngestionRepository(":memory:", [retention, retention])
