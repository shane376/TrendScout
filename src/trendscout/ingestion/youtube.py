"""Bounded official YouTube Data API client and canonical ingestion adapter."""

import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from .base import CollectionError
from .models import CollectionRequest, CollectionResult, CollectionRun, ContentItem, NativeMetrics, as_utc

SOURCE_ID = "youtube.data-api-v3"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class YouTubeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    max_search_pages: int = Field(default=2, ge=1, le=5)
    details_batch_size: int = Field(default=50, ge=1, le=50)
    max_attempts: int = Field(default=3, ge=1, le=3)
    connect_timeout: float = Field(default=5, gt=0, le=120, allow_inf_nan=False)
    read_timeout: float = Field(default=20, gt=0, le=120, allow_inf_nan=False)

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(**{
            name: os.environ[variable] for name, variable in {
                "api_key": "YOUTUBE_API_KEY", "max_search_pages": "YOUTUBE_MAX_SEARCH_PAGES",
                "details_batch_size": "YOUTUBE_DETAILS_BATCH_SIZE", "max_attempts": "YOUTUBE_MAX_ATTEMPTS",
                "connect_timeout": "YOUTUBE_CONNECT_TIMEOUT", "read_timeout": "YOUTUBE_READ_TIMEOUT",
            }.items() if variable in os.environ
        })


class MissingYouTubeKey(CollectionError):
    def __init__(self):
        super().__init__(SOURCE_ID, "access_denied")
        self.args = ("YOUTUBE_API_KEY is required for live collection. Configure it or explicitly use --fixture.",)


class YouTubeClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3/"

    def __init__(self, config: YouTubeConfig, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        if not config.api_key.get_secret_value().strip():
            raise MissingYouTubeKey()
        self.config = config
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._sleep = sleep

    def close(self):
        if self._owns_session:
            self._session.close()

    @staticmethod
    def _reasons(response) -> set[str]:
        try:
            payload = response.json()
        except ValueError:
            return set()
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return set()
        reasons = {error["status"]} if isinstance(error.get("status"), str) else set()
        for group in ("errors", "details"):
            entries = error.get(group)
            if isinstance(entries, list):
                reasons.update(entry["reason"] for entry in entries
                               if isinstance(entry, dict) and isinstance(entry.get("reason"), str))
        return reasons

    def _get(self, method: str, params: dict) -> dict:
        for attempt in range(self.config.max_attempts):
            try:
                response = self._session.request(
                    "GET", self.BASE_URL + method, params=params,
                    headers={"X-Goog-Api-Key": self.config.api_key.get_secret_value().strip()},
                    timeout=(self.config.connect_timeout, self.config.read_timeout), allow_redirects=False,
                )
            except (requests.Timeout, requests.ConnectionError):
                if attempt + 1 == self.config.max_attempts:
                    raise CollectionError(SOURCE_ID, "unavailable") from None
                self._sleep(2 ** attempt)
                continue
            except requests.RequestException:
                raise CollectionError(SOURCE_ID, "unavailable") from None
            reasons = self._reasons(response) if response.status_code >= 400 else set()
            if response.status_code == 429 or reasons & {
                "quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg", "rateLimitExceeded",
                "userRateLimitExceeded", "RESOURCE_EXHAUSTED", "RATE_LIMIT_EXCEEDED", "QUOTA_EXCEEDED",
            }:
                raise CollectionError(SOURCE_ID, "rate_limited")
            if response.status_code in (500, 502, 503, 504):
                if attempt + 1 == self.config.max_attempts:
                    raise CollectionError(SOURCE_ID, "unavailable")
                self._sleep(2 ** attempt)
                continue
            if response.status_code in (401, 403) or reasons & {
                "keyInvalid", "API_KEY_INVALID", "accessNotConfigured", "PERMISSION_DENIED", "UNAUTHENTICATED",
            }:
                raise CollectionError(SOURCE_ID, "access_denied")
            if response.status_code != 200:
                raise CollectionError(SOURCE_ID, "invalid_response")
            try:
                payload = response.json()
            except ValueError:
                raise CollectionError(SOURCE_ID, "invalid_response") from None
            if not isinstance(payload, dict) or "error" in payload or not isinstance(payload.get("items"), list):
                raise CollectionError(SOURCE_ID, "invalid_response")
            return payload
        raise CollectionError(SOURCE_ID, "unavailable")

    def search(self, query: str, limit: int, page_token: str | None = None) -> dict:
        if not 1 <= limit <= 50:
            raise ValueError("Search page size must be 1–50")
        params = {"part": "snippet", "type": "video", "q": query, "maxResults": limit,
                  "fields": "nextPageToken,items(id(kind,videoId))"}
        if page_token is not None:
            params["pageToken"] = page_token
        return self._get("search", params)

    def videos(self, ids: list[str]) -> dict:
        if not 1 <= len(ids) <= 50 or any(not VIDEO_ID.fullmatch(video_id) for video_id in ids):
            raise ValueError("Details requests require 1–50 valid video identifiers")
        return self._get("videos", {
            "part": "snippet,statistics", "id": ",".join(ids),
            "fields": "items(id,snippet(title,description,channelTitle,publishedAt),statistics(viewCount,likeCount,commentCount))",
        })


def normalize_video(record: dict, collected_at: datetime, *, source_id: str = SOURCE_ID,
                    synthetic: bool = False) -> ContentItem:
    """Allowlist canonical metadata. No raw payload, durations, or inferred Shorts labels."""
    video_id = record["id"]
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid video identifier")
    snippet = record["snippet"]
    title = snippet["title"]
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Missing video title")
    publication = snippet["publishedAt"]
    if not isinstance(publication, str):
        raise ValueError("Invalid publication timestamp")
    published_at = as_utc(datetime.fromisoformat(publication))
    metrics = None
    if "statistics" in record:
        stats = record["statistics"]
        if not isinstance(stats, dict):
            raise ValueError("Invalid statistics")
        values = {}
        for native, name in (("viewCount", "views"), ("likeCount", "likes"), ("commentCount", "comments")):
            value = stats.get(native)
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
                    raise ValueError("Invalid native counter")
                value = int(value)
            values[name] = value
        metrics = NativeMetrics(observed_at=collected_at, values=values)
    url = f"https://www.youtube.com/watch?v={video_id}" if not synthetic else f"https://example.com/trendscout/youtube/{video_id}"
    return ContentItem(
        platform="youtube", external_id=video_id, source_id=source_id,
        provenance="synthetic" if synthetic else "live",
        attribution="Synthetic YouTube fixture; not live evidence" if synthetic else "YouTube Data API v3",
        content_type="video", title=title, description=snippet.get("description"),
        creator=snippet.get("channelTitle"), published_at=published_at, collected_at=collected_at,
        url=url, metrics=metrics,
    )


class YouTubeSource:
    def __init__(self, config: YouTubeConfig | None = None, *, client=None, fixture: bool = False,
                 clock: Callable[[], datetime] | None = None):
        if fixture and client is not None:
            raise ValueError("Fixture mode cannot use a live client")
        self.source_id = "youtube.fixture" if fixture else SOURCE_ID
        self._fixture = fixture
        self.config = config or (YouTubeConfig() if fixture else YouTubeConfig.from_env())
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if fixture:
            from .youtube_fixture import FixtureYouTubeClient
            self._client = FixtureYouTubeClient()
        else:
            self._client = client if client is not None else YouTubeClient(self.config)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._client.close()

    def collect(self, request: CollectionRequest) -> CollectionResult:
        request = CollectionRequest.model_validate(request.model_dump())
        if request.source_id != self.source_id:
            raise CollectionError(self.source_id, "wrong_source")
        started = as_utc(self._clock())
        items, rejected, codes = [], 0, []
        seen_ids, seen_tokens = set(), set()
        token = None
        for page in range(self.config.max_search_pages):
            remaining = request.limit - len(items) - rejected
            if remaining <= 0:
                break
            try:
                payload = self._client.search(request.query, min(50, remaining), token)
                rows = payload["items"]
                next_token = payload.get("nextPageToken")
                if not isinstance(rows, list) or len(rows) > min(50, remaining):
                    raise CollectionError(self.source_id, "invalid_response")
                if next_token is not None and (not isinstance(next_token, str) or not next_token.strip()):
                    raise CollectionError(self.source_id, "invalid_response")
                ids = []
                for row in rows:
                    identity = row.get("id") if isinstance(row, dict) else None
                    video_id = identity.get("videoId") if isinstance(identity, dict) else None
                    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id) or identity.get("kind") != "youtube#video":
                        rejected += 1
                        codes.append("invalid_record")
                    elif video_id not in seen_ids:
                        seen_ids.add(video_id)
                        ids.append(video_id)
                for offset in range(0, len(ids), self.config.details_batch_size):
                    chunk = ids[offset:offset + self.config.details_batch_size]
                    details = self._client.videos(chunk)["items"]
                    if not isinstance(details, list) or len(details) > len(chunk):
                        raise CollectionError(self.source_id, "invalid_response")
                    mapped = {}
                    for row in details:
                        identity = row.get("id") if isinstance(row, dict) else None
                        if not isinstance(identity, str) or identity not in chunk:
                            codes.append("invalid_response")
                        elif identity in mapped:
                            mapped[identity] = None
                        else:
                            mapped[identity] = row
                    collected = as_utc(self._clock())
                    for video_id in chunk:
                        if mapped.get(video_id) is None:
                            rejected += 1
                            codes.append("missing_video")
                            continue
                        try:
                            items.append(normalize_video(mapped[video_id], collected, source_id=self.source_id, synthetic=self._fixture))
                        except (KeyError, TypeError, ValueError, ValidationError):
                            rejected += 1
                            codes.append("invalid_record")
            except CollectionError as error:
                codes.append(error.code)
                break
            if not next_token or len(items) + rejected >= request.limit:
                break
            if next_token in seen_tokens:
                codes.append("pagination_cycle")
                break
            seen_tokens.add(next_token)
            token = next_token
            if page + 1 == self.config.max_search_pages:
                codes.append("page_limit")
        completed = as_utc(self._clock())
        status = "complete" if not codes else ("partial" if items else "failed")
        return CollectionResult(run=CollectionRun(
            source_id=self.source_id, provenance="synthetic" if self._fixture else "live",
            started_at=started, completed_at=completed, requested_limit=request.limit,
            item_count=len(items), rejected_count=rejected, status=status,
            error_codes=tuple(dict.fromkeys(codes)),
        ), items=tuple(items))
