from datetime import datetime

from ..models import AnalyzedPost, ContentPost
from .scoring import normalize, recency


def rank_posts(posts: list[ContentPost], now: datetime) -> list[AnalyzedPost]:
    # Stable identity tie-break, independent of input ordering.
    unique = {(p.platform, p.id): p for p in posts}
    candidates = sorted(unique.values(), key=lambda p: (p.platform, p.id))
    engagement = normalize([p.score for p in candidates])
    discussion = normalize([p.comment_count for p in candidates])
    analyzed = []
    for post, eng, disc in zip(candidates, engagement, discussion):
        recent = recency(post.created_at, now)
        analyzed.append(AnalyzedPost(post=post, engagement_score=eng,
            discussion_score=disc, recency_score=recent,
            opportunity_score=eng * .5 + recent * .3 + disc * .2, rank=1))
    analyzed.sort(key=lambda p: (-p.opportunity_score, p.post.platform, p.post.id))
    return [p.model_copy(update={"rank": i}) for i, p in enumerate(analyzed, 1)]
