"""Explicit synthetic responses; this module has no HTTP transport."""

import json
from importlib.resources import files


class FixtureYouTubeClient:
    def __init__(self):
        self._records = json.loads(files("trendscout").joinpath("data/youtube_fixture.json").read_text(encoding="utf-8"))["videos"]

    def search(self, query: str, limit: int, page_token: str | None = None) -> dict:
        return {"items": [{"id": {"kind": "youtube#video", "videoId": record["id"]}}
                          for record in self._records[:limit]]}

    def videos(self, ids: list[str]) -> dict:
        return {"items": [record for record in self._records if record["id"] in ids]}

    def close(self):
        pass
