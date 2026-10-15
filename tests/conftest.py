from datetime import datetime, timezone

import pytest

from trendscout.models import ContentPost


@pytest.fixture
def now():
    return datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def post(now):
    return ContentPost(id="test", platform="reddit", title="Testing an AI workflow",
        score=100, comment_count=10, created_at=now,
        url="https://www.reddit.com/r/test/comments/test/example/")
