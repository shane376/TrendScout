import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import AnalyzedPost, VideoIdea


def spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def markdown_text(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", value)


def export_results(posts: list[AnalyzedPost], ideas: list[VideoIdea], root: Path) -> Path:
    stamp = datetime.now(timezone.utc)
    for _ in range(1000):
        folder = root / stamp.strftime("%Y-%m-%d_%H%M%S_%fZ")
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            # Clock resolution can repeat a timestamp; never overwrite an existing run.
            stamp = max(datetime.now(timezone.utc), stamp + timedelta(microseconds=1))
        else:
            break
    else:
        raise FileExistsError("Could not allocate a unique export directory after 1000 attempts.")
    fields = ["rank", "id", "platform", "title", "body", "author", "community", "url", "created_at", "score", "comment_count", "engagement_score", "recency_score", "discussion_score", "opportunity_score"]
    with (folder / "ranked_posts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in posts:
            row = item.post.model_dump(mode="json")
            row.update(item.model_dump(exclude={"post"}))
            writer.writerow({key: spreadsheet_safe(value) for key, value in row.items()})
    (folder / "content_ideas.json").write_text(
        json.dumps([idea.model_dump(mode="json") for idea in ideas], ensure_ascii=False, indent=2), encoding="utf-8")
    sections = ["# TrendScout Content Ideas", "Template-generated research drafts. Fact-check before production."]
    for i, idea in enumerate(ideas, 1):
        sections.extend([
            f"## Idea {i}: {markdown_text(idea.title)}",
            f"Mode: {idea.mode} | Generator: {idea.generation_method}",
            f"Source: {idea.source_url}",
            f"Source title: {markdown_text(idea.source_title)}",
            f"Niche: {markdown_text(idea.target_niche)}",
            f"Opportunity Score: {idea.opportunity_score:.2f}",
            "### Content Angle", markdown_text(idea.content_angle),
            "### Hook", markdown_text(idea.hook),
            "### Script", markdown_text(idea.script),
            "### Visual Suggestions", "\n".join(f"- {markdown_text(v)}" for v in idea.suggested_visuals),
            "### Call to Action", markdown_text(idea.call_to_action),
            f"Fact-check required: {idea.fact_check_note}",
        ])
    (folder / "scripts.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return folder
