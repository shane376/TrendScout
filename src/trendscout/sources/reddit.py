import logging
import time
from typing import Any

import requests
from pydantic import ValidationError

from ..config import Settings
from ..models import ContentPost
from .base import SourceError

logger = logging.getLogger(__name__)


def parse_records(children: list[Any]) -> list[ContentPost]:
    posts = []
    seen = set()
    for child in children:
        try:
            data = child["data"]
            if data.get("over_18") or data.get("stickied"):
                continue
            post = ContentPost(
                id=data["id"], platform="reddit", title=data["title"],
                body=data.get("selftext"), author=data.get("author"),
                score=data.get("score"), comment_count=data.get("num_comments"),
                created_at=data["created_utc"],
                url="https://www.reddit.com" + data["permalink"],
                community=data.get("subreddit"),
            )
            if post.id not in seen:
                posts.append(post)
                seen.add(post.id)
        except (KeyError, TypeError, ValueError, ValidationError):
            logger.warning("Skipped malformed Reddit record")
    return posts


class RedditSource:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        if not all((settings.client_id, settings.client_secret, settings.user_agent)):
            raise SourceError("Live Reddit requires REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET and REDDIT_USER_AGENT. Configure approved access or use --demo.")
        self.settings = settings
        self.session = session or requests.Session()

    def _request(self, method: str, url: str, **kwargs) -> dict:
        for attempt in range(3):
            try:
                response = self.session.request(method, url, timeout=(5, 20), **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise SourceError("Reddit connection failed after three attempts.") from None
                time.sleep(2 ** attempt)
                continue
            except requests.RequestException:
                raise SourceError("Reddit request failed.") from None
            if response.status_code == 429:
                # Stop instead of risking a retry before Reddit's rate window resets.
                raise SourceError("Reddit rate limit reached. Wait before running again.")
            if response.status_code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if not 200 <= response.status_code < 300:
                raise SourceError(f"Reddit returned HTTP {response.status_code}; check approved API access.")
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError
                return payload
            except ValueError:
                raise SourceError("Reddit returned invalid JSON.") from None
        raise SourceError("Reddit is temporarily unavailable.")

    def collect(self, niche: str, candidate_limit: int) -> list[ContentPost]:
        token = self._request(
            "POST", "https://www.reddit.com/api/v1/access_token",
            auth=(self.settings.client_id, self.settings.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.settings.user_agent},
        ).get("access_token")
        if not isinstance(token, str) or not token:
            raise SourceError("Reddit did not grant an access token.")
        payload = self._request(
            "GET", "https://oauth.reddit.com/search",
            headers={"User-Agent": self.settings.user_agent, "Authorization": f"Bearer {token}"},
            params={"q": niche, "sort": "relevance", "t": "month", "limit": min(candidate_limit, 100), "type": "link"},
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("children"), list):
            raise SourceError("Reddit returned an invalid search listing.")
        return parse_records(data["children"])
