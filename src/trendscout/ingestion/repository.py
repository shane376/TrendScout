"""Small transactional SQLite repository with opt-in source retention policies."""

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .models import CollectionResult, CollectionRun, ContentItem, NativeMetrics, RetentionPolicy, as_utc
from .schema import MIGRATION_1, TABLES, VERSION


class PersistenceError(ValueError):
    """Invalid/replayed batch or storage not permitted by an explicit source policy."""


def timestamp(value: datetime) -> str:
    return as_utc(value).isoformat(timespec="microseconds")


class IngestionRepository:
    def __init__(self, database: Path | str, policies: Iterable[RetentionPolicy] = ()):
        self._policies = {}
        for policy in policies:
            policy = RetentionPolicy.model_validate(policy.model_dump())
            if policy.source_id in self._policies:
                raise ValueError("Duplicate retention policy for source")
            self._policies[policy.source_id] = policy
        self._connection = sqlite3.connect(database, isolation_level=None, timeout=5)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            with self._transaction():
                version = self._connection.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    if self._connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                        raise PersistenceError("Refusing to adopt an unversioned existing database")
                    for statement in MIGRATION_1:
                        self._connection.execute(statement)
                    self._connection.execute("PRAGMA user_version = 1")
                elif version != VERSION:
                    raise PersistenceError("Unsupported ingestion database schema version")
        except Exception:
            self.close()
            raise

    @contextmanager
    def _transaction(self):
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._connection.close()

    def save(self, result: CollectionResult, *, now: datetime | None = None) -> UUID:
        # Revalidate at the boundary, including objects created via model_copy/model_construct.
        result = CollectionResult.model_validate(result.model_dump())
        now = as_utc(now or datetime.now(timezone.utc))
        run = result.run
        policy = self._policies.get(run.source_id)
        if policy is None or run.provenance == "unknown" or (run.provenance == "live" and not policy.allow_live):
            raise PersistenceError("Persistence requires an explicit source policy and permitted provenance")
        if run.completed_at > now:
            raise PersistenceError("Collection cannot complete after persistence time")
        prepared = []
        for item in result.items:
            expiry = item.collected_at + policy.ttl
            if item.expires_at is not None:
                expiry = min(expiry, item.expires_at)
            metric_expiry = None
            if item.metrics is not None:
                metric_expiry = min(expiry, item.metrics.observed_at + policy.ttl)
                if item.metrics.expires_at is not None:
                    metric_expiry = min(metric_expiry, item.metrics.expires_at)
            if expiry <= now or (metric_expiry is not None and metric_expiry <= now):
                raise PersistenceError("Batch contains expired source data or observations")
            prepared.append((item, expiry, metric_expiry))

        canonical = json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        run_id = str(run.run_id)
        with self._transaction():
            existing = self._connection.execute(
                "SELECT run_json, batch_digest FROM collection_runs WHERE run_id=?", (run_id,),
            ).fetchone()
            if existing is not None:
                same_batch = existing["batch_digest"] == digest or (
                    not result.items and existing["batch_digest"] is None
                )
                if existing["run_json"] != run.model_dump_json() or not same_batch:
                    raise PersistenceError("Run ID already recorded with different or expired batch data")
                return run.run_id
            self._connection.execute(
                "INSERT INTO collection_runs VALUES (?, ?, ?, ?, ?)",
                (run_id, run.source_id, timestamp(run.completed_at), run.model_dump_json(), digest),
            )
            for item, expiry, metric_expiry in prepared:
                item_id = item.item_id
                self._connection.execute(
                    "INSERT INTO content_items VALUES (?, ?, ?) ON CONFLICT(platform, external_id) DO NOTHING",
                    (item_id, item.platform, item.external_id),
                )
                record = item.model_dump(mode="json", exclude={"metrics"})
                record["expires_at"] = timestamp(expiry)
                self._connection.execute(
                    """INSERT INTO item_records VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(item_id, source_id) DO UPDATE SET
                        collected_at=excluded.collected_at, expires_at=excluded.expires_at,
                        record_json=excluded.record_json
                    WHERE excluded.collected_at >= item_records.collected_at""",
                    (item_id, item.source_id, timestamp(item.collected_at), timestamp(expiry), json.dumps(record)),
                )
                self._connection.execute(
                    "INSERT INTO run_items VALUES (?, ?, ?, ?, ?)",
                    (run_id, item_id, item.source_id, timestamp(item.collected_at), timestamp(expiry)),
                )
                if item.metrics is not None:
                    metrics = item.metrics
                    values = json.dumps(metrics.values, sort_keys=True)
                    previous = self._connection.execute(
                        "SELECT values_json FROM metric_observations WHERE item_id=? AND source_id=? AND observed_at=?",
                        (item_id, item.source_id, timestamp(metrics.observed_at)),
                    ).fetchone()
                    if previous is not None and previous[0] != values:
                        raise PersistenceError("Conflicting metric values for an existing observation timestamp")
                    self._connection.execute(
                        """INSERT INTO metric_observations VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(item_id, source_id, observed_at) DO UPDATE SET
                            expires_at=MIN(metric_observations.expires_at, excluded.expires_at)""",
                        (item_id, item.source_id, timestamp(metrics.observed_at), timestamp(metric_expiry), values),
                    )
        return run.run_id

    def get_run(self, run_id: UUID | str) -> CollectionRun | None:
        row = self._connection.execute("SELECT run_json FROM collection_runs WHERE run_id=?", (str(run_id),)).fetchone()
        return CollectionRun.model_validate_json(row[0]) if row else None

    def get_item(self, platform: str, external_id: str, source_id: str, *, now: datetime | None = None) -> ContentItem | None:
        now_text = timestamp(now or datetime.now(timezone.utc))
        row = self._connection.execute(
            """SELECT r.item_id, r.record_json FROM item_records r JOIN content_items c USING(item_id)
            WHERE c.platform=? AND c.external_id=? AND r.source_id=? AND r.expires_at>?""",
            (platform, external_id, source_id, now_text),
        ).fetchone()
        if row is None:
            return None
        record = json.loads(row["record_json"])
        metric = self._connection.execute(
            """SELECT * FROM metric_observations WHERE item_id=? AND source_id=? AND expires_at>?
            ORDER BY observed_at DESC LIMIT 1""", (row["item_id"], source_id, now_text),
        ).fetchone()
        if metric:
            record["metrics"] = self._metrics(metric).model_dump()
        return ContentItem.model_validate(record)

    @staticmethod
    def _metrics(row) -> NativeMetrics:
        return NativeMetrics(observed_at=row["observed_at"], expires_at=row["expires_at"], values=json.loads(row["values_json"]))

    def get_observations(self, item_id: str, source_id: str, *, now: datetime | None = None) -> list[NativeMetrics]:
        cutoff = timestamp(now or datetime.now(timezone.utc))
        rows = self._connection.execute(
            """SELECT m.* FROM metric_observations m JOIN item_records r USING(item_id, source_id)
            WHERE item_id=? AND source_id=? AND m.expires_at>? AND r.expires_at>? ORDER BY observed_at""",
            (item_id, source_id, cutoff, cutoff),
        )
        return [self._metrics(row) for row in rows]

    def counts(self) -> dict[str, int]:
        """Operational row counts, including expired records until purged."""
        # Only fixed schema identifiers are interpolated; all user data uses bound parameters.
        return {table: self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}

    def purge_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        cutoff = timestamp(now or datetime.now(timezone.utc))
        with self._transaction():
            before = self.counts()
            self._connection.execute("DELETE FROM metric_observations WHERE expires_at<=?", (cutoff,))
            self._connection.execute("DELETE FROM run_items WHERE expires_at<=?", (cutoff,))
            self._connection.execute("DELETE FROM item_records WHERE expires_at<=?", (cutoff,))
            self._connection.execute("DELETE FROM content_items WHERE NOT EXISTS (SELECT 1 FROM item_records r WHERE r.item_id=content_items.item_id)")
            # Drop content-derived replay fingerprints once a run retains no source associations.
            self._connection.execute("""UPDATE collection_runs SET batch_digest=NULL
                WHERE NOT EXISTS (SELECT 1 FROM run_items r WHERE r.run_id=collection_runs.run_id)""")
            after = self.counts()
        return {table: before[table] - after[table] for table in TABLES}
