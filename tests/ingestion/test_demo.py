from trendscout.ingestion.demo import run_demo


def test_offline_workflow(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline ingestion must not use the network")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    result = run_demo()
    assert result["before_expiration"] == {
        "content_items": 3, "item_records": 3, "collection_runs": 2,
        "run_items": 6, "metric_observations": 4,
    }
    assert result["after_expiration"]["collection_runs"] == 2
    assert result["after_expiration"]["content_items"] == 0
