from trendscout.analysis.ranking import rank_posts
from trendscout.generation.quality import evaluate_quality
from trendscout.generation.templates import TemplateGenerator
from trendscout.generation.quality import QualityWarning
from trendscout.cli import app
from typer.testing import CliRunner


def make_idea(post, now):
    return TemplateGenerator().generate(rank_posts([post], now), "AI", "demo")[0]


def codes(ideas):
    return {warning.code for warning in evaluate_quality(ideas)}


def test_empty_and_complete(post, now):
    assert evaluate_quality([]) == []
    assert evaluate_quality([make_idea(post, now)]) == []


def test_duplicates_and_near_duplicates(post, now):
    idea = make_idea(post, now)
    assert {"duplicate_hook", "repetitive_scripts"} <= codes([idea, idea])
    near = idea.model_copy(update={"hook": idea.hook.replace("evidence", "proof")})
    assert "similar_hooks" in codes([idea, near])
    changed_title = idea.model_copy(update={
        "source_title": "A different title", "hook": "An entirely different opening?",
        "script": idea.script.replace(idea.hook, "An entirely different opening?").replace(post.title, "A different title"),
    })
    assert "repetitive_scripts" in codes([idea, changed_title])


def test_missing_sections_and_short_script(post, now):
    idea = make_idea(post, now).model_copy(update={"hook": "", "script": "A tiny script.", "suggested_visuals": []})
    warnings = evaluate_quality([idea])
    assert {"missing_sections", "short_script"} <= {w.code for w in warnings}
    message = next(w.message for w in warnings if w.code == "missing_sections")
    assert all(section in message for section in ("hook", "Problem", "Explanation", "Demonstration", "Takeaway", "suggested_visuals"))
    assert all(w.idea_numbers == (1,) and w.message for w in warnings)


def test_empty_labeled_section(post, now):
    idea = make_idea(post, now)
    script = "Problem:\n\nExplanation: An explanation.\n\nDemonstration: A plan.\n\nTakeaway: A next step."
    warnings = evaluate_quality([idea.model_copy(update={"script": script})])
    assert "Problem" in next(w.message for w in warnings if w.code == "missing_sections")


def test_filler_attribution_and_fact_check(post, now):
    idea = make_idea(post, now).model_copy(update={
        "hook": "This GAME-CHANGING tool will unlock your potential!",
        "source_id": "", "source_url": None,
        "requires_fact_check": False, "fact_check_note": "",
    })
    assert {"generic_filler", "missing_attribution", "missing_fact_check"} <= codes([idea])


def test_excessive_length_and_determinism(post, now):
    idea = make_idea(post, now).model_copy(update={"script": "word " * 161})
    assert "long_script" in codes([idea])
    assert evaluate_quality([idea, idea]) == evaluate_quality([idea, idea])


def test_identical_hooks_ignore_punctuation_and_case(post, now):
    idea = make_idea(post, now)
    changed = idea.model_copy(update={"hook": idea.hook.upper().replace("?", "!")})
    assert "duplicate_hook" in codes([idea, changed])


def test_cli_reports_advisory_warnings_without_changing_exports(monkeypatch, tmp_path):
    import json
    import trendscout.cli as cli

    monkeypatch.setattr(cli, "evaluate_quality", lambda ideas: [
        QualityWarning("similar_hooks", (1, 2), "Rewrite one opening around a different question.")
    ])
    result = CliRunner().invoke(app, ["run", "--niche", "AI tools", "--limit", "5", "--demo", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Ideas 1, 2 [similar_hooks]" in result.output
    assert "Rewrite one opening" in result.output
    folder = next(tmp_path.iterdir())
    data = json.loads((folder / "content_ideas.json").read_text(encoding="utf-8"))
    assert len(data) == 5
    assert "quality_warnings" not in data[0]
    assert {p.name for p in folder.iterdir()} == {"content_ideas.json", "ranked_posts.csv", "scripts.md"}
