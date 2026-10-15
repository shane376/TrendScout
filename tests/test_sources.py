from unittest.mock import Mock, patch

import pytest
import requests
from pydantic import ValidationError

from trendscout.config import Settings
from trendscout.models import ContentPost
from trendscout.sources.base import SourceError
from trendscout.sources.reddit import RedditSource, parse_records


def response(status=200, payload=None):
    result = Mock(status_code=status)
    result.json.return_value = payload
    return result


def source(session):
    return RedditSource(Settings(client_id="test-id", client_secret="test-secret", user_agent="test-agent"), session)


def test_missing_credentials():
    with pytest.raises(SourceError, match="--demo"):
        RedditSource(Settings())


def test_malformed_records():
    good = {"data": {"id": "1", "title": "  A &amp; B \n", "created_utc": 1700000000,
        "permalink": "/r/test/comments/1/title/", "score": None, "num_comments": None}}
    posts = parse_records([None, {}, {"data": {}}, good, good])
    assert len(posts) == 1
    assert posts[0].title == "A & B"
    assert posts[0].score == posts[0].comment_count == 0


def test_invalid_model(post):
    data = post.model_dump()
    for updates in ({"title": " "}, {"url": "file:///test"}, {"created_at": "2026-01-01"}, {"comment_count": -1}):
        with pytest.raises(ValidationError):
            ContentPost.model_validate(data | updates)


def test_authorized_request():
    session = Mock()
    session.request.side_effect = [response(payload={"access_token": "token"}), response(payload={"data": {"children": []}})]
    assert source(session).collect("AI tools", 25) == []
    calls = session.request.call_args_list
    assert calls[0].kwargs["data"] == {"grant_type": "client_credentials"}
    assert calls[1].args[1] == "https://oauth.reddit.com/search"
    assert calls[1].kwargs["headers"]["Authorization"] == "Bearer token"
    assert calls[1].kwargs["params"]["limit"] == 25


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_errors_do_not_retry(status):
    session = Mock()
    session.request.return_value = response(status)
    with pytest.raises(SourceError):
        source(session).collect("AI", 25)
    assert session.request.call_count == 1


@patch("trendscout.sources.reddit.time.sleep")
def test_bounded_timeout_retries(sleep):
    session = Mock()
    session.request.side_effect = requests.Timeout()
    with pytest.raises(SourceError, match="three attempts"):
        source(session).collect("AI", 25)
    assert session.request.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


@patch("trendscout.sources.reddit.time.sleep")
def test_server_retry_then_success(sleep):
    session = Mock()
    session.request.side_effect = [response(503), response(payload={"access_token": "t"}), response(payload={"data": {"children": []}})]
    assert source(session).collect("AI", 25) == []
    assert sleep.call_count == 1


@pytest.mark.parametrize("payload", [None, [], {}, {"access_token": ""}])
def test_bad_token_payload(payload):
    session = Mock()
    session.request.return_value = response(payload=payload)
    with pytest.raises(SourceError):
        source(session).collect("AI", 25)


def test_invalid_json_and_listing():
    session = Mock()
    bad = response()
    bad.json.side_effect = ValueError
    session.request.return_value = bad
    with pytest.raises(SourceError, match="invalid JSON"):
        source(session).collect("AI", 25)
    session.request.side_effect = [response(payload={"access_token": "t"}), response(payload={"data": {"children": None}})]
    with pytest.raises(SourceError, match="invalid search listing"):
        source(session).collect("AI", 25)
