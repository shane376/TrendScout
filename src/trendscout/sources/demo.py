import json
from importlib.resources import files

from ..models import ContentPost


class DemoSource:
    def collect(self, niche: str, candidate_limit: int) -> list[ContentPost]:
        # Deliberately fixed dates and clearly synthetic records, never live fallback.
        payload = json.loads(files("trendscout").joinpath("data/sample_posts.json").read_text(encoding="utf-8"))
        return [ContentPost.model_validate(record) for record in payload][:candidate_limit]
