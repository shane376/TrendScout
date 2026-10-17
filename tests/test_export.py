import csv
import json
from datetime import timedelta
from unittest.mock import Mock

import pytest

from trendscout.analysis.ranking import rank_posts
from trendscout.exporters.export import export_results
from trendscout.generation.templates import TemplateGenerator


def test_exports(post, now, tmp_path):
    post = post.model_copy(update={"title": '=HYPERLINK("bad") café, "quoted"'})
    ranked = rank_posts([post], now)
    ideas = TemplateGenerator().generate(ranked, "AI", "demo")
    folder = export_results(ranked, ideas, tmp_path / "nested")
    with (folder / "ranked_posts.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["title"] == "'" + post.title
    assert float(rows[0]["opportunity_score"]) == ranked[0].opportunity_score
    data = json.loads((folder / "content_ideas.json").read_text(encoding="utf-8"))
    assert data[0]["source_url"] == str(post.url)
    assert data[0]["mode"] == "demo"
    markdown = (folder / "scripts.md").read_text(encoding="utf-8")
    assert "### Hook" in markdown and "### Script" in markdown and "café" in markdown
    assert export_results(ranked, ideas, tmp_path / "nested") != folder


def test_exports_with_repeated_clock_timestamp(post, now, tmp_path, monkeypatch):
    import trendscout.exporters.export as exporter

    monkeypatch.setattr(exporter, "datetime", Mock(now=Mock(return_value=now)))
    ranked = rank_posts([post], now)
    ideas = TemplateGenerator().generate(ranked, "AI", "demo")
    first = export_results(ranked, ideas, tmp_path)
    original = {path.name: path.read_bytes() for path in first.iterdir()}
    second = export_results(ranked, ideas, tmp_path)
    assert first.name == now.strftime("%Y-%m-%d_%H%M%S_%fZ")
    assert second.name == (now + timedelta(microseconds=1)).strftime("%Y-%m-%d_%H%M%S_%fZ")
    assert {path.name: path.read_bytes() for path in first.iterdir()} == original
    assert {path.name: path.read_bytes() for path in second.iterdir()} == original


def test_export_permission_error_is_not_retried(post, now, tmp_path, monkeypatch):
    import trendscout.exporters.export as exporter

    mkdir = Mock(side_effect=PermissionError("not writable"))
    monkeypatch.setattr(exporter.Path, "mkdir", mkdir)
    with pytest.raises(PermissionError, match="not writable"):
        export_results(rank_posts([post], now), [], tmp_path)
    assert mkdir.call_count == 1
