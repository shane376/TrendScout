from datetime import timedelta

import pytest

from trendscout.analysis.ranking import rank_posts
from trendscout.analysis.scoring import normalize, recency


def test_normalization():
    assert normalize([]) == []
    assert normalize([0, 0]) == [0, 0]
    assert normalize([10, 10]) == [0, 0]
    values = normalize([-4, 0, 10, 100])
    assert values[:2] == [0, 0]
    assert 0 < values[2] < 100
    assert values[-1] == 100


def test_recency(now):
    assert recency(now, now) == 100
    assert recency(now - timedelta(hours=72), now) == pytest.approx(50)
    assert recency(now + timedelta(days=1), now) == 100
    assert recency(now - timedelta(days=10000), now) >= 0
    with pytest.raises(ValueError):
        recency(now, now, 0)
    with pytest.raises(ValueError):
        recency(now.replace(tzinfo=None), now)


def test_rankings(post, now):
    other = post.model_copy(update={"id": "a"})
    first = rank_posts([post, other], now)
    assert first == rank_posts([other, post], now)
    assert [p.post.id for p in first] == ["a", "test"]
    assert [p.rank for p in first] == [1, 2]
    assert all(0 <= p.opportunity_score <= 100 for p in first)
    assert len(rank_posts([post, post], now)) == 1
    assert rank_posts([], now) == []


def test_weights(post, now):
    weak = post.model_copy(update={"id": "weak", "score": 0, "comment_count": 0})
    assert rank_posts([post, weak], now)[0].opportunity_score == 100
