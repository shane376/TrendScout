from datetime import timedelta

import pytest

from trendscout.ingestion.models import CollectionResult, CollectionRun, ContentItem, NativeMetrics


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Intelligence tests must not make real HTTP requests")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("trendscout.ingestion.youtube.load_dotenv", lambda: None)
    for variable in ("YOUTUBE_API_KEY", "YOUTUBE_MAX_SEARCH_PAGES", "YOUTUBE_DETAILS_BATCH_SIZE",
                     "YOUTUBE_MAX_ATTEMPTS", "YOUTUBE_CONNECT_TIMEOUT", "YOUTUBE_READ_TIMEOUT"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def make_result(now):
    def make(*changes, status="complete", provenance="synthetic"):
        items = []
        for index, change in enumerate(changes or ({},)):
            data = dict(
                platform="youtube", external_id=f"video-{index}", source_id="youtube.fixture",
                provenance=provenance, attribution="Synthetic test fixture", content_type="video",
                title="Automation workflow review", description="Compare one documented workflow.",
                creator="Synthetic channel", url=f"https://example.com/{index}",
                published_at=now - timedelta(days=10), collected_at=now,
                metrics=NativeMetrics(observed_at=now, values={"views": 1000, "likes": 50, "comments": 10}),
            )
            data.update(change)
            items.append(ContentItem.model_validate(data))
        run = CollectionRun(
            source_id="youtube.fixture", provenance=provenance, started_at=now, completed_at=now,
            requested_limit=100, item_count=len(items), status=status,
            error_codes=("page_limit",) if status == "partial" else (),
        )
        return CollectionResult(run=run, items=tuple(items))
    return make
