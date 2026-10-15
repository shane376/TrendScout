from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .analysis.ranking import rank_posts
from .config import Settings
from .exporters.export import export_results
from .generation.base import IdeaGenerator
from .generation.templates import TemplateGenerator
from .models import AnalyzedPost, VideoIdea
from .sources.base import ContentSource, SourceError
from .sources.demo import DemoSource
from .sources.reddit import RedditSource


@dataclass
class PipelineResult:
    posts: list[AnalyzedPost]
    ideas: list[VideoIdea]
    output_dir: Path
    candidate_count: int


def run_pipeline(niche: str, limit: int, settings: Settings, demo: bool = False,
                 source: ContentSource | None = None, generator: IdeaGenerator | None = None,
                 now: datetime | None = None) -> PipelineResult:
    niche = " ".join(niche.split())
    if not niche or len(niche) > 200 or not 1 <= limit <= 20:
        raise ValueError("Provide a niche of 1-200 characters and a limit from 1 to 20.")
    if source is None:
        if demo:
            source = DemoSource()
        elif settings.content_source == "reddit":
            source = RedditSource(settings)
        else:
            raise SourceError(f"Unsupported CONTENT_SOURCE: {settings.content_source}")
    posts = source.collect(niche, min(100, max(25, limit * 5)))
    if not posts:
        raise SourceError("No valid posts found. Try a broader niche or a different time.")
    ranked = rank_posts(posts, now or datetime.now(timezone.utc))
    selected = ranked[:limit]
    ideas = (generator or TemplateGenerator()).generate(selected, niche, "demo" if demo else "live")
    folder = export_results(ranked, ideas, settings.output_dir)
    return PipelineResult(ranked, ideas, folder, len(ranked))
