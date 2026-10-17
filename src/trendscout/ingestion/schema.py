"""Schema 1. Migrations run atomically, guarded by PRAGMA user_version."""

VERSION = 1
TABLES = ("content_items", "item_records", "collection_runs", "run_items", "metric_observations")
MIGRATION_1 = (
    """CREATE TABLE content_items (
        item_id TEXT PRIMARY KEY,
        platform TEXT NOT NULL,
        external_id TEXT NOT NULL,
        UNIQUE(platform, external_id)
    )""",
    """CREATE TABLE item_records (
        item_id TEXT NOT NULL REFERENCES content_items(item_id) ON DELETE CASCADE,
        source_id TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY(item_id, source_id),
        CHECK(expires_at > collected_at)
    )""",
    """CREATE TABLE collection_runs (
        run_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        run_json TEXT NOT NULL,
        batch_digest TEXT
    )""",
    """CREATE TABLE run_items (
        run_id TEXT NOT NULL REFERENCES collection_runs(run_id) ON DELETE CASCADE,
        item_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        PRIMARY KEY(run_id, item_id),
        FOREIGN KEY(item_id, source_id) REFERENCES item_records(item_id, source_id) ON DELETE CASCADE,
        CHECK(expires_at > collected_at)
    )""",
    """CREATE TABLE metric_observations (
        item_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        values_json TEXT NOT NULL,
        PRIMARY KEY(item_id, source_id, observed_at),
        FOREIGN KEY(item_id, source_id) REFERENCES item_records(item_id, source_id) ON DELETE CASCADE,
        CHECK(expires_at > observed_at)
    )""",
    "CREATE INDEX records_expiry ON item_records(expires_at)",
    "CREATE INDEX records_source ON item_records(source_id, collected_at)",
    "CREATE INDEX observations_expiry ON metric_observations(expires_at)",
    "CREATE INDEX links_expiry ON run_items(expires_at)",
    "CREATE INDEX links_item ON run_items(item_id, source_id)",
    "CREATE INDEX runs_source ON collection_runs(source_id, completed_at)",
)
