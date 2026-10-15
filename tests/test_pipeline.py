import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from trendscout.cli import app
from trendscout.config import Settings
from trendscout.pipeline import run_pipeline
from trendscout.sources.base import SourceError


def test_demo_pipeline(tmp_path, now):
    result = run_pipeline("AI tools", 5, Settings(output_dir=tmp_path), demo=True, now=now)
    assert result.candidate_count == 25
    assert len(result.ideas) == 5
    assert len(list(result.output_dir.iterdir())) == 3
    data = json.loads((result.output_dir / "content_ideas.json").read_text(encoding="utf-8"))
    assert len(data) == 5
    assert all(item["mode"] == "demo" for item in data)


def test_empty_source(tmp_path):
    with pytest.raises(SourceError, match="No valid posts"):
        run_pipeline("AI", 5, Settings(output_dir=tmp_path), source=Mock(collect=Mock(return_value=[])))
    assert not list(tmp_path.iterdir())


def test_candidate_limit_and_shortfall(post, now, tmp_path):
    source = Mock(collect=Mock(return_value=[post]))
    result = run_pipeline("AI", 5, Settings(output_dir=tmp_path), source=source, now=now)
    source.collect.assert_called_once_with("AI", 25)
    assert len(result.ideas) == 1


@pytest.mark.parametrize("args", [["--limit", "0"], ["--limit", "21"], ["--niche", " "], ["--niche", "x" * 201]])
def test_cli_validation(args):
    result = CliRunner().invoke(app, ["run", "--niche", "AI", "--demo", *args])
    assert result.exit_code == 2


def test_cli_help_and_demo(tmp_path):
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["run", "--niche", "AI tools", "--limit", "5", "--demo", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "DEMO" in result.output and "generated 5" in result.output


def test_cli_missing_credentials(monkeypatch):
    monkeypatch.setattr(Settings, "from_env", lambda: Settings())
    result = CliRunner().invoke(app, ["run", "--niche", "AI tools"])
    assert result.exit_code == 1
    assert "REDDIT_CLIENT_ID" in result.output
