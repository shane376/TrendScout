"""Validate existing exports without collecting, generating, or changing them."""

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from trendscout.models import AnalyzedPost, VideoIdea


@dataclass
class RunData:
    posts: list[AnalyzedPost] = field(default_factory=list)
    ideas: list[VideoIdea] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    posts_available: bool = False
    ideas_available: bool = False
    quality_warnings: list | None = None
    quality_status: str = "Quality evaluator unavailable on this branch."
    provenance: str = "Unknown — exports do not verify collection provenance."


def discover_runs(root: Path) -> list[Path]:
    """Newest first, using the exporter timestamp; include partial/empty runs."""
    if not root.exists():
        return []
    runs = []
    for path in root.iterdir():
        if not path.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{6}_\d{6}Z", path.name):
            continue
        try:
            stamp = datetime.strptime(path.name, "%Y-%m-%d_%H%M%S_%fZ")
        except ValueError:
            continue
        runs.append((stamp, path))
    return [path for _, path in sorted(runs, reverse=True)]


def load_run(folder: Path) -> RunData:
    result = RunData()
    try:
        with (folder / "ranked_posts.csv").open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"rank", "id", "platform", "title", "url", "created_at",
                        "opportunity_score", "engagement_score", "recency_score", "discussion_score"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("missing required CSV columns")
            identities = set()
            ranks = set()
            for number, row in enumerate(reader, 2):
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("incorrect column count")
                    # CSV spreadsheet escapes are intentionally preserved, not guessed away.
                    post = {key: row[key] for key in ("id", "platform", "title", "url", "created_at")}
                    post.update({key: row.get(key) or None for key in ("body", "author", "community")})
                    post.update({key: row.get(key) or None for key in ("score", "comment_count")})
                    item = AnalyzedPost.model_validate({"post": post, **{key: row[key] for key in
                        ("rank", "opportunity_score", "engagement_score", "recency_score", "discussion_score")}})
                    identity = (item.post.platform, item.post.id)
                    if identity in identities or item.rank in ranks:
                        raise ValueError("duplicate identity or rank")
                    identities.add(identity)
                    ranks.add(item.rank)
                    result.posts.append(item)
                except (ValidationError, ValueError):
                    result.issues.append(f"ranked_posts.csv row {number}: invalid record excluded.")
            result.posts_available = True
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        result.posts.clear()
        result.issues.append(f"ranked_posts.csv unavailable: {error}")

    try:
        raw = json.loads((folder / "content_ideas.json").read_text(encoding="utf-8-sig"))
        if not isinstance(raw, list):
            raise ValueError("expected a JSON list")
        for number, record in enumerate(raw, 1):
            try:
                # Do not let model defaults invent missing fact-check metadata.
                required = set(VideoIdea.model_fields)
                if not isinstance(record, dict) or not required.issubset(record):
                    raise ValueError("missing exported fields")
                result.ideas.append(VideoIdea.model_validate(record))
            except (ValidationError, ValueError):
                result.issues.append(f"content_ideas.json idea {number}: invalid record excluded.")
        result.ideas_available = True
    except (OSError, UnicodeError, ValueError) as error:
        result.issues.append(f"content_ideas.json unavailable: {error}")

    if result.ideas and result.ideas_available and not any("content_ideas.json" in issue for issue in result.issues):
        modes = {idea.mode for idea in result.ideas}
        platforms = {post.post.platform for post in result.posts} | {idea.source_platform for idea in result.ideas}
        if modes == {"demo"} and (not platforms or platforms == {"demo"}):
            result.provenance = "Synthetic demo — exported mode is demo; not live trends."
        elif modes == {"live"} and "demo" not in platforms:
            result.provenance = "Live-labeled export — collection verification unknown."
        else:
            result.provenance = "Unknown — mixed or unrecognized mode/source labels."

    if result.ideas_available and not any("content_ideas.json" in issue for issue in result.issues):
        try:
            from trendscout.generation.quality import evaluate_quality
        except ModuleNotFoundError as error:
            if error.name != "trendscout.generation.quality":
                raise
        else:
            result.quality_warnings = evaluate_quality(result.ideas)
            result.quality_status = "Recomputed from this complete exported idea batch using the installed evaluator; not historical results."
    elif result.issues:
        result.quality_status = "Quality unavailable: idea export is missing or invalid; batch evaluation would be incomplete."
    return result
