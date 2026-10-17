import csv
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from trendscout.config import Settings
from trendscout.dashboard.data import discover_runs, load_run
from trendscout.pipeline import run_pipeline


@pytest.fixture
def exported(tmp_path, now):
    return run_pipeline("AI tools", 5, Settings(output_dir=tmp_path), demo=True, now=now)


def rewrite_csv(folder, change):
    path = folder / "ranked_posts.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    change(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_demo_roundtrip(exported):
    data = load_run(exported.output_dir)
    assert len(data.posts) == 25 and len(data.ideas) == 5
    assert data.posts == exported.posts
    assert data.ideas == exported.ideas
    assert not data.issues
    assert data.provenance.startswith("Synthetic demo")
    assert data.quality_warnings is None


def test_discovery(tmp_path):
    names = ["2026-10-16_120000_000001Z", "2026-10-15_120000_000001Z"]
    for name in [*names, "2026-99-15_120000_000001Z", "2026-1-15_120000_000001Z", "random"]:
        (tmp_path / name).mkdir()
    (tmp_path / "2026-10-17_120000_000001Z").write_text("")
    assert [p.name for p in discover_runs(tmp_path)] == names
    assert discover_runs(tmp_path / "absent") == []


def test_missing_and_invalid_files(tmp_path):
    data = load_run(tmp_path)
    assert len(data.issues) == 2
    assert not data.posts_available and not data.ideas_available
    assert data.provenance.startswith("Unknown")
    (tmp_path / "ranked_posts.csv").write_text("title\nonly title\n")
    (tmp_path / "content_ideas.json").write_text('{}')
    assert len(load_run(tmp_path).issues) == 2
    (tmp_path / "content_ideas.json").write_bytes(b"\xff")
    assert len(load_run(tmp_path).issues) == 2


@pytest.mark.parametrize("value", ["", "NaN", "inf", "101", "-1"])
def test_bad_scores_are_excluded(exported, value):
    rewrite_csv(exported.output_dir, lambda rows: rows[0].update(opportunity_score=value))
    data = load_run(exported.output_dir)
    assert len(data.posts) == 24
    assert "row 2" in data.issues[0]


def test_empty_optional_metrics_and_duplicate(exported):
    def change(rows):
        rows[0].update(body="", author="", score="", comment_count="")
        rows.append(rows[0].copy())
    rewrite_csv(exported.output_dir, change)
    data = load_run(exported.output_dir)
    assert data.posts[0].post.score == 0
    assert data.posts[0].post.body is None
    assert len(data.posts) == 25 and len(data.issues) == 1


@pytest.mark.parametrize("mode", ["live", "unrecognized"])
def test_provenance_never_verifies_live(exported, mode):
    path = exported.output_dir / "content_ideas.json"
    records = json.loads(path.read_text(encoding='utf-8'))
    for record in records:
        record["mode"] = mode
    path.write_text(json.dumps(records))
    assert load_run(exported.output_dir).provenance.startswith("Unknown")  # demo CSV conflicts
    rewrite_csv(exported.output_dir, lambda rows: [row.update(platform="reddit") for row in rows])
    for record in records:
        record["source_platform"] = "reddit"
    path.write_text(json.dumps(records), encoding="utf-8")
    data = load_run(exported.output_dir)
    assert "verification unknown" in data.provenance if mode == "live" else data.provenance.startswith("Unknown")


def test_quality_uses_complete_batch_only(exported, monkeypatch):
    module = ModuleType("trendscout.generation.quality")
    calls = []
    module.evaluate_quality = lambda ideas: calls.append(ideas) or ["existing evaluator result"]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    data = load_run(exported.output_dir)
    assert data.quality_warnings == ["existing evaluator result"]
    assert calls == [exported.ideas]
    path = exported.output_dir / "content_ideas.json"
    records = json.loads(path.read_text(encoding='utf-8'))
    del records[0]["requires_fact_check"]
    path.write_text(json.dumps(records))
    data = load_run(exported.output_dir)
    assert len(data.ideas) == 4 and data.issues
    assert data.quality_warnings is None and len(calls) == 1
    assert data.provenance.startswith("Unknown")


def test_valid_empty_exports(exported):
    rewrite_csv(exported.output_dir, lambda rows: rows.clear())
    (exported.output_dir / "content_ideas.json").write_text("[]")
    data = load_run(exported.output_dir)
    assert data.posts_available and data.ideas_available
    assert not data.posts and not data.ideas and not data.issues


def test_dashboard_interactions(exported, monkeypatch, tmp_path):
    testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("OUTPUT_DIR", str(exported.output_dir.parent))
    app = testing.AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard/app.py").run(timeout=30)
    assert not app.exception
    assert [metric.value for metric in app.metric][:2] == ["25", "5"]
    assert len(app.expander) == 5
    app.selectbox(key="candidate-inspect").select(1).run()
    assert not app.exception
    assert any(exported.posts[1].post.title in item.value for item in app.text)
    app.text_input(key="candidate-query").set_value("no-matching-title").run()
    assert not app.exception
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    app.text_input(key="output-root").set_value(str(tmp_path / "missing")).run()
    assert not app.exception
    assert any("No timestamped runs" in item.value for item in app.info)


def test_dashboard_partial_run(tmp_path, monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    folder = tmp_path / "2026-10-17_120000_000001Z"
    folder.mkdir()
    (folder / "content_ideas.json").write_text("invalid", encoding="utf-8")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    app = testing.AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard/app.py").run(timeout=30)
    assert not app.exception
    assert len(app.warning) == 2
    assert all(metric.value == "Unavailable" for metric in app.metric)
