import csv
import json

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
