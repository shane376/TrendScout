import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from pydantic import ValidationError

from trendscout.ingestion.base import CollectionError, IngestionSource
from trendscout.ingestion.models import CollectionRequest, CollectionResult, RetentionPolicy
from trendscout.ingestion.repository import IngestionRepository, PersistenceError
from trendscout.ingestion.youtube import (
    SOURCE_ID, MissingYouTubeKey, YouTubeClient, YouTubeConfig, YouTubeSource, normalize_video,
)
from trendscout.ingestion.youtube_demo import main

KEY = "unit-test-key-not-a-real-credential"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("YouTube tests must not access the network")
    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr("trendscout.ingestion.youtube.load_dotenv", lambda: None)
    for variable in ("YOUTUBE_API_KEY", "YOUTUBE_MAX_SEARCH_PAGES", "YOUTUBE_DETAILS_BATCH_SIZE",
                     "YOUTUBE_MAX_ATTEMPTS", "YOUTUBE_CONNECT_TIMEOUT", "YOUTUBE_READ_TIMEOUT"):
        monkeypatch.delenv(variable, raising=False)


def response(payload=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = {"items": []} if payload is None else payload
    return result


def search(*ids, token=None):
    payload = {"items": [{"id": {"kind": "youtube#video", "videoId": identity}} for identity in ids]}
    if token is not None:
        payload["nextPageToken"] = token
    return payload


def video(identity="video-id-001", **changes):
    return {"id": identity, "snippet": {
        "title": "A synthetic mocked API record", "description": "Offline HTTP fixture, not live evidence.",
        "channelTitle": "Example channel", "publishedAt": "2026-01-01T12:00:00Z",
    }, "statistics": {"viewCount": "100", "likeCount": "2", "commentCount": "0"}, **changes}


def source_with_responses(now, responses, **config):
    session = Mock()
    session.request.side_effect = responses
    sleep = Mock()
    client = YouTubeClient(YouTubeConfig(api_key=KEY, **config), session=session, sleep=sleep)
    source = YouTubeSource(client.config, client=client, clock=lambda: now)
    return source, session, sleep


def collect(source, limit=10):
    return source.collect(CollectionRequest(source_id=source.source_id, query="AI automation", limit=limit))


def test_official_requests_and_canonical_result(now, caplog):
    source, session, _ = source_with_responses(now, [response(search("video-id-001")), response({"items": [video()]})])
    assert isinstance(source, IngestionSource)
    result = collect(source)
    assert CollectionResult.model_validate_json(result.model_dump_json()) == result
    assert result.run.status == "complete" and result.run.item_count == 1
    assert result.run.provenance == "live" and result.run.source_id == SOURCE_ID
    item = result.items[0]
    assert item.platform == "youtube" and item.external_id == "video-id-001"
    assert item.content_type == "video" and "short" not in item.content_type
    assert str(item.url) == "https://www.youtube.com/watch?v=video-id-001"
    assert item.metrics.values == {"views": 100, "likes": 2, "comments": 0}
    calls = session.request.call_args_list
    assert [call.args for call in calls] == [
        ("GET", "https://www.googleapis.com/youtube/v3/search"),
        ("GET", "https://www.googleapis.com/youtube/v3/videos"),
    ]
    assert calls[0].kwargs["params"]["type"] == "video"
    assert calls[1].kwargs["params"]["part"] == "snippet,statistics"
    assert calls[0].kwargs["headers"] == {"X-Goog-Api-Key": KEY}
    assert calls[0].kwargs["timeout"] == (5, 20)
    assert calls[0].kwargs["allow_redirects"] is False
    assert all("key" not in call.kwargs["params"] for call in calls)
    assert KEY not in caplog.text + result.model_dump_json() + repr(source.config) + source.config.model_dump_json()


def test_missing_key_and_wrong_source(now):
    with pytest.raises(MissingYouTubeKey, match="YOUTUBE_API_KEY"):
        YouTubeClient(YouTubeConfig())
    source = YouTubeSource(fixture=True, clock=lambda: now)
    with pytest.raises(CollectionError, match="different source"):
        source.collect(CollectionRequest(source_id=SOURCE_ID, query="test"))


@pytest.mark.parametrize("status,reason,code", [
    (401, "authError", "access_denied"), (403, "forbidden", "access_denied"),
    (400, "keyInvalid", "access_denied"), (403, "quotaExceeded", "rate_limited"),
    (403, "dailyLimitExceeded", "rate_limited"), (403, "rateLimitExceeded", "rate_limited"),
    (429, "", "rate_limited"), (400, "badRequest", "invalid_response"), (302, "", "invalid_response"),
])
def test_nonretryable_errors_are_safe(now, caplog, status, reason, code):
    payload = {"error": {"message": KEY, "errors": [{"reason": reason}]}}
    source, session, sleep = source_with_responses(now, [response(payload, status)])
    result = collect(source)
    assert result.run.status == "failed" and result.run.error_codes == (code,)
    assert not result.items and result.run.rejected_count == 0
    assert session.request.call_count == 1
    sleep.assert_not_called()
    assert KEY not in result.model_dump_json() + caplog.text


@pytest.mark.parametrize("error", [requests.Timeout(KEY), requests.ConnectionError(KEY), 500, 502, 503, 504])
def test_transient_errors_retry_with_bounds(now, error):
    first = response(status=error) if isinstance(error, int) else error
    source, session, sleep = source_with_responses(now, [first, response(search()), ])
    assert collect(source).run.status == "complete"
    assert session.request.call_count == 2
    sleep.assert_called_once_with(1)


def test_retry_exhaustion_and_no_secret_leak(now):
    source, session, sleep = source_with_responses(now, [requests.Timeout(KEY)] * 3)
    result = collect(source)
    assert result.run.error_codes == ("unavailable",)
    assert session.request.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
    assert KEY not in result.model_dump_json()


@pytest.mark.parametrize("payload", [[], {}, {"items": None}, {"items": {}}, {"items": [], "error": {}}])
def test_invalid_api_envelopes(now, payload):
    source, session, _ = source_with_responses(now, [response(payload)])
    assert collect(source).run.error_codes == ("invalid_response",)
    assert session.request.call_count == 1


def test_invalid_json(now):
    invalid = response()
    invalid.json.side_effect = ValueError(KEY)
    source, _, _ = source_with_responses(now, [invalid])
    result = collect(source)
    assert result.run.error_codes == ("invalid_response",)
    assert KEY not in result.model_dump_json()


def test_missing_statistics_are_not_zero(now):
    record = video()
    del record["statistics"]
    assert normalize_video(record, now).metrics is None
    record["statistics"] = {"viewCount": "0"}
    assert normalize_video(record, now).metrics.values == {"views": 0, "likes": None, "comments": None}


@pytest.mark.parametrize("statistics", [{"viewCount": "-1"}, {"likeCount": 1}, {"commentCount": True}, {"viewCount": "NaN"}, []])
def test_invalid_counters_reject_only_affected_record(now, statistics):
    source, _, _ = source_with_responses(now, [
        response(search("good", "bad")), response({"items": [video("good"), video("bad", statistics=statistics)]}),
    ])
    result = collect(source)
    assert result.run.status == "partial" and result.run.rejected_count == 1
    assert [item.external_id for item in result.items] == ["good"]


def test_duplicates_pagination_and_details_batching(now):
    source, session, _ = source_with_responses(now, [
        response(search("a", "a", token="page-2")), response({"items": [video("a")]}),
        response(search("a", "b", "c")), response({"items": [video("b")]}), response({"items": [video("c")]}),
    ], details_batch_size=1)
    result = collect(source, limit=5)
    assert result.run.status == "complete" and [item.external_id for item in result.items] == ["a", "b", "c"]
    assert session.request.call_args_list[2].kwargs["params"]["pageToken"] == "page-2"
    details = [call for call in session.request.call_args_list if call.args[1].endswith("/videos")]
    assert [call.kwargs["params"]["id"] for call in details] == ["a", "b", "c"]


def test_pagination_cap_and_repeated_token(now):
    source, session, _ = source_with_responses(now, [response(search("a", token="more")), response({"items": [video("a")]})], max_search_pages=1)
    result = collect(source)
    assert result.run.status == "partial" and result.run.error_codes == ("page_limit",)
    assert session.request.call_count == 2
    source, session, _ = source_with_responses(now, [
        response(search("a", token="same")), response({"items": [video("a")]}), response(search("a", token="same")),
    ])
    assert collect(source).run.error_codes == ("pagination_cycle",)
    assert session.request.call_count == 3


def test_no_more_calls_after_requested_limit(now):
    source, session, _ = source_with_responses(now, [response(search("a", token="more")), response({"items": [video("a")]})])
    assert collect(source, limit=1).run.status == "complete"
    assert session.request.call_count == 2


def test_partial_results_survive_later_quota_error(now):
    source, session, sleep = source_with_responses(now, [
        response(search("a", token="more")), response({"items": [video("a")]}), response(status=429),
    ])
    result = collect(source)
    assert result.run.status == "partial" and result.run.item_count == 1
    assert result.run.error_codes == ("rate_limited",)
    assert session.request.call_count == 3
    sleep.assert_not_called()


def test_rejected_search_and_missing_details(now):
    payload = search("a", "missing")
    payload["items"].append({"id": {"kind": "youtube#channel", "channelId": "not-video"}})
    source, _, _ = source_with_responses(now, [response(payload), response({"items": [video("a")]})])
    result = collect(source)
    assert result.run.status == "partial" and result.run.rejected_count == 2
    assert set(result.run.error_codes) == {"invalid_record", "missing_video"}


def test_publication_and_collection_timestamps(now):
    source, _, _ = source_with_responses(now, [response(search("a")), response({"items": [video("a")]})])
    times = iter([now, now + timedelta(seconds=1), now + timedelta(seconds=2)])
    source._clock = lambda: next(times)
    result = collect(source)
    assert result.run.started_at == now and result.run.completed_at == now + timedelta(seconds=2)
    assert result.items[0].collected_at == result.items[0].metrics.observed_at == now + timedelta(seconds=1)
    assert result.items[0].published_at.utcoffset() == timedelta(0)
    record = video()
    record["snippet"]["publishedAt"] = "2026-01-01T12:00:00"
    with pytest.raises(ValueError, match="timezone"):
        normalize_video(record, now)


def test_fixture_cli_writes_no_source_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    assert main(["--query", "AI automation", "--limit", "10", "--fixture"]) == 0
    output = capsys.readouterr().out
    assert "SYNTHETIC FIXTURE" in output and "accepted: 3" in output
    assert '"likes":null' in output and "No source data written" in output
    assert KEY not in output and list(tmp_path.iterdir()) == []


def test_cli_errors_and_never_falls_back(monkeypatch, capsys):
    monkeypatch.setattr("trendscout.ingestion.youtube.load_dotenv", lambda: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert main(["--query", "test"]) == 1
    assert "YOUTUBE_API_KEY is required" in capsys.readouterr().out
    assert main(["--query", "test", "--limit", "101", "--fixture"]) == 2
    capsys.readouterr()
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    monkeypatch.setattr(requests.Session, "request", Mock(return_value=response(status=403)))
    assert main(["--query", "test"]) == 1
    output = capsys.readouterr().out
    assert "access_denied" in output and "SYNTHETIC FIXTURE" not in output and KEY not in output


def test_persistence_still_requires_explicit_retention(now, tmp_path):
    source, _, _ = source_with_responses(now, [response(search("a")), response({"items": [video("a")]})])
    result = collect(source)
    policy = RetentionPolicy(source_id=SOURCE_ID, ttl=timedelta(hours=1))
    with IngestionRepository(tmp_path / "youtube.sqlite3", [policy]) as repository:
        with pytest.raises(PersistenceError):
            repository.save(result, now=now)
        assert not any(repository.counts().values())
    # Explicit opt-in tested only on mocked data; it is not permission for live API data storage.
    with IngestionRepository(":memory:", [policy.model_copy(update={"allow_live": True})]) as repository:
        repository.save(result, now=now)
        assert repository.get_item("youtube", "a", SOURCE_ID, now=now).metrics.values["views"] == 100
        assert "api_key" not in repository._connection.execute("SELECT record_json FROM item_records").fetchone()[0]
        repository.purge_expired(now=now + policy.ttl)
        assert repository.counts()["content_items"] == 0


@pytest.mark.parametrize("config", [
    {"max_search_pages": 6}, {"details_batch_size": 51}, {"max_attempts": 4},
    {"connect_timeout": 0}, {"read_timeout": float("inf")},
])
def test_configuration_bounds(config):
    with pytest.raises(ValidationError):
        YouTubeConfig(**config)


def test_env_configuration_and_safe_repr(monkeypatch):
    monkeypatch.setattr("trendscout.ingestion.youtube.load_dotenv", lambda: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    monkeypatch.setenv("YOUTUBE_READ_TIMEOUT", "12")
    config = YouTubeConfig.from_env()
    assert config.read_timeout == 12 and KEY not in repr(config)


@pytest.mark.parametrize("error", [
    {"errors": None, "details": [{"reason": "QUOTA_EXCEEDED"}]},
    {"status": "RESOURCE_EXHAUSTED"},
])
def test_quota_on_transient_status_is_never_retried(now, error):
    source, session, sleep = source_with_responses(now, [response({"error": error}, status=503)])
    assert collect(source).run.error_codes == ("rate_limited",)
    assert session.request.call_count == 1
    sleep.assert_not_called()


def test_full_hundred_record_limit_and_fifty_id_requests(now):
    first = [f"first-{number}" for number in range(50)]
    second = [f"second-{number}" for number in range(50)]
    source, session, _ = source_with_responses(now, [
        response(search(*first, token="second-page")), response({"items": [video(identity) for identity in first]}),
        response(search(*second, token="unused-page")), response({"items": [video(identity) for identity in second]}),
    ])
    result = collect(source, limit=100)
    assert result.run.status == "complete" and len(result.items) == 100
    assert session.request.call_count == 4
    assert all(len(call.kwargs["params"]["id"].split(",")) == 50
               for call in session.request.call_args_list if call.args[1].endswith("/videos"))


@pytest.mark.parametrize("record", [
    {"id": "bad", "snippet": None}, {"id": "bad", "snippet": {}},
    {"id": "bad", "snippet": {"title": "text", "publishedAt": "nonsense"}},
])
def test_incomplete_video_preserves_valid_siblings(now, record):
    source, _, _ = source_with_responses(now, [response(search("good", "bad")), response({"items": [video("good"), record]})])
    result = collect(source)
    assert result.run.status == "partial" and result.run.rejected_count == 1
    assert result.run.item_count == 1 and result.run.error_codes == ("invalid_record",)


def test_extraneous_details_and_empty_search_do_not_create_content(now):
    source, session, _ = source_with_responses(now, [response(search())])
    assert collect(source).items == () and session.request.call_count == 1
    source, _, _ = source_with_responses(now, [response(search("expected")), response({"items": [video("unsolicited")]})])
    result = collect(source)
    assert not result.items and result.run.rejected_count == 1
    assert "invalid_response" in result.run.error_codes


def test_duplicate_details_are_rejected(now):
    source, _, _ = source_with_responses(now, [
        response(search("a", "b", "c")), response({"items": [video("a"), video("a"), video("c")]}),
    ])
    result = collect(source)
    assert [item.external_id for item in result.items] == ["c"]
    assert result.run.rejected_count == 2


@pytest.mark.parametrize("token", ["", 123, {}])
def test_invalid_page_tokens_stop_collection(now, token):
    payload = search("a")
    payload["nextPageToken"] = token
    source, session, _ = source_with_responses(now, [response(payload)])
    assert collect(source).run.status == "failed"
    assert session.request.call_count == 1


def test_fixture_does_not_load_live_settings(monkeypatch):
    monkeypatch.setenv("YOUTUBE_MAX_SEARCH_PAGES", "invalid-live-setting")
    monkeypatch.setattr("trendscout.ingestion.youtube.load_dotenv", Mock(side_effect=AssertionError("Fixture must not load .env")))
    with YouTubeSource(fixture=True) as source:
        result = collect(source, limit=1)
    assert result.run.provenance == "synthetic" and len(result.items) == 1


def test_mocked_live_cli_does_not_persist(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    transport = Mock(side_effect=[response(search("a")), response({"items": [video("a")]})])
    monkeypatch.setattr(requests.Session, "request", transport)
    assert main(["--query", "test", "--limit", "1"]) == 0
    output = capsys.readouterr().out
    assert "LIVE" in output and "accepted: 1" in output and KEY not in output
    assert transport.call_count == 2 and list(tmp_path.iterdir()) == []
